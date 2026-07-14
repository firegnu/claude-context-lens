"""Ingest a Codex CLI rollout log into the frozen on-disk contract.

Codex writes each session as `~/.codex/sessions/<Y>/<M>/<D>/rollout-*.jsonl` — a
linear, ordered event stream. This module replays that stream and reconstructs a
per-model-call view, then maps it into the SAME `session.json` / breakdown shape
the Claude side produces, so the macOS app renders Codex sessions unchanged.

Scope so far: `event_msg.user_message` starts a turn; each turn is decomposed into
model calls delimited by `event_msg.token_count`; each call's five layers are filled
from turn_context / base+developer / messages+tool-calls / (no tool schemas) /
agent+reasoning, with usage from token_count (see `_segment_calls` and
`codex_breakdown`). Later tickets add compaction handling and multi-agent.
"""
import json
from collections import Counter
from pathlib import Path

from .contract import write_json, validate_session
from .codex_breakdown import build_codex_breakdown

# Event kinds the ingest actually consumes. Every other kind seen in a rollout is
# counted as skipped (see _event_accounting) so real-rollout surprises surface in
# the contract instead of being silently dropped. Keep this in lockstep with what
# the reconstruction (`_segment_calls`) AND detection (`_is_multi_agent`) read —
# e.g. `compacted` (boundary) and `inter_agent_communication_metadata` (multi-agent
# signal) — or the accounting misreports consumed kinds as skipped.
# `response_item.message` is intentionally NOT here: only its developer-role variant
# is consumed (L2); role=user (injected context) and role=assistant are not, so the
# kind stays flagged as not-fully-consumed.
_CONSUMED_EVENT_KINDS = frozenset({
    "session_meta",
    "turn_context",
    "event_msg.user_message",
    "event_msg.agent_message",
    "event_msg.token_count",
    "response_item.reasoning",
    "response_item.function_call",
    "response_item.custom_tool_call",
    "response_item.function_call_output",
    "response_item.custom_tool_call_output",
    "compacted",
    "event_msg.context_compacted",
    "inter_agent_communication_metadata",
})


def _read_events(rollout_path):
    """Parse a rollout line-by-line into JSON objects, tolerating a hostile file.

    Blank lines, unparseable lines, and lines that aren't JSON objects are skipped
    and tallied rather than raised, so a single bad line can't abort the ingest.
    Returns (events, malformed_lines)."""
    events = []
    malformed = 0
    with Path(rollout_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if not isinstance(obj, dict):
                malformed += 1
                continue
            events.append(obj)
    return events, malformed


def _payload(event):
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _event_kind(event):
    """A stable accounting key: the top-level type, refined by payload.type for the
    envelope types (event_msg / response_item) whose meaning lives in the payload."""
    etype = event.get("type")
    if etype in ("event_msg", "response_item"):
        ptype = _payload(event).get("type")
        if ptype:
            return f"{etype}.{ptype}"
    return etype or "<untyped>"


def _event_accounting(events, malformed_lines):
    by_kind = Counter(_event_kind(event) for event in events)
    skipped = {kind: count for kind, count in by_kind.items()
               if kind not in _CONSUMED_EVENT_KINDS}
    return {
        "events_total": len(events),
        "malformed_lines": malformed_lines,
        "events_by_kind": dict(by_kind),
        "skipped_kinds": dict(sorted(skipped.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def _session_meta(events):
    for event in events:
        if event.get("type") == "session_meta":
            return _payload(event)
    return {}


def _first_model(events):
    for event in events:
        if event.get("type") == "turn_context":
            model = _payload(event).get("model")
            if model:
                return model
    return None


def _is_multi_agent(events):
    """True only if the session actually ran multiple agents. The authoritative
    signal is the `inter_agent_communication_metadata` event. The turn_context
    `multi_agent_mode` / `collaboration_mode` / `multi_agent_version` fields are NOT
    used: measured across 200 real rollouts they are config defaults present in
    single-agent sessions too (multi_agent_mode="explicitRequestOnly",
    collaboration_mode.mode="default", version="v1"/"v2"), so flagging on them would
    misclassify every session. Only ~1 in 4 "v2" sessions ever emit an inter-agent
    event — that event is what marks a real multi-agent run."""
    return any(event.get("type") == "inter_agent_communication_metadata"
               for event in events)


def _message_text(payload):
    """Text of a response_item.message payload, whose content is [{text}] or a str."""
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content
                       if isinstance(part, dict))
    return ""


def _new_call():
    return {"user_messages": [], "reasoning_count": 0, "agent_messages": [],
            "tool_calls": [], "tool_outputs": {}, "compaction_count": 0}


def _call_has_activity(call):
    # A lone compaction boundary is NOT model activity: real rollouts always follow
    # `compacted` with a token_count, so it attaches to that call. A trailing
    # compaction with no following call (only in synthetic fixtures) is not promoted
    # to a spurious request.
    return bool(call["user_messages"] or call["reasoning_count"]
                or call["agent_messages"] or call["tool_calls"])


def _finalize_call(call, base_instructions, developer_messages, turn_context, usage):
    """Turn accumulated per-call raw events into a `call` dict for build_codex_breakdown.
    Tool calls are paired with their outputs by call_id."""
    tool_calls = [{"name": tc["name"], "arguments": tc["arguments"], "call_id": tc["call_id"],
                   "output": call["tool_outputs"].get(tc["call_id"])}
                  for tc in call["tool_calls"]]
    return {
        "turn_context": dict(turn_context),
        "base_instructions": base_instructions,
        "developer_messages": list(developer_messages),
        "user_messages": list(call["user_messages"]),
        "tool_calls": tool_calls,
        "agent_messages": list(call["agent_messages"]),
        "reasoning_count": call["reasoning_count"],
        "compaction_count": call["compaction_count"],
        "usage": usage,
    }


def _segment_calls(events, base_instructions):
    """Segment the event stream into turns, each decomposed into model calls.

    Turn boundary = ``event_msg.user_message`` (ticket 03 decision). A real rollout
    also carries role=user ``response_item.message`` items, but those include
    Codex-injected context (``<environment_context>``, ``<user_instructions>``,
    compaction fill-ins) and consistently over-count (e.g. 171 vs 135 in one scanned
    session; see research-rollout-format.md), so segmenting on them would invent
    spurious turns. Injected content is context for the breakdown, not a turn start.

    Call boundary = ``event_msg.token_count`` — Codex emits one usage record per
    model response, so each token_count closes one model call (ticket 04). A turn's
    trailing model activity with no closing token_count (e.g. the simplified
    fixtures, or an aborted turn) is finalized as one call with usage=None, so a
    token_count-less stream degrades to one aggregate call per turn.

    Each call's L3 is that call's own activity (new user message, tool calls +
    results, agent text), NOT a verbatim replay of the whole prior context: history
    is periodically compacted, so a full replay could be wrong. `compacted` events
    are flagged as boundaries on the call they precede — their replacement_history is
    never replayed (ticket 05 safe stance) — and v1 keeps an honest per-call/local
    view rather than an over-complete one.

    Returns [{"user": str, "calls": [call_dict, ...]}].
    """
    turns = []
    developer_messages = []
    turn_context = {}
    current_turn = None
    call = _new_call()

    def close_call(usage):
        nonlocal call
        if current_turn is not None and (_call_has_activity(call) or usage is not None):
            current_turn["calls"].append(_finalize_call(
                call, base_instructions, developer_messages, turn_context, usage))
        call = _new_call()

    for event in events:
        etype = event.get("type")
        payload = _payload(event)
        if etype == "turn_context":
            turn_context = payload
        elif etype == "compacted":
            # History was compacted here; flag the boundary on the current call.
            # replacement_history is deliberately NOT read — no pre-compaction replay
            # (ticket 05 safe stance). context_compacted (event_msg) always pairs with
            # this event, so it is not counted again.
            call["compaction_count"] += 1
        elif etype == "response_item":
            ptype = payload.get("type")
            if ptype == "message" and payload.get("role") == "developer":
                developer_messages.append(_message_text(payload))
            elif ptype == "reasoning":
                call["reasoning_count"] += 1
            elif ptype in ("function_call", "custom_tool_call"):
                call["tool_calls"].append({
                    "name": payload.get("name"),
                    "arguments": payload.get("arguments", payload.get("input")),
                    "call_id": payload.get("call_id")})
            elif ptype in ("function_call_output", "custom_tool_call_output"):
                call["tool_outputs"][payload.get("call_id")] = payload.get("output")
        elif etype == "event_msg":
            ptype = payload.get("type")
            if ptype == "user_message":
                close_call(None)          # close any in-flight call before the new turn
                if current_turn is not None:
                    turns.append(current_turn)
                current_turn = {"user": payload.get("message") or "", "calls": []}
                call["user_messages"].append(current_turn["user"])
            elif ptype == "agent_message":
                call["agent_messages"].append(payload.get("message") or "")
            elif ptype == "token_count":
                close_call(payload.get("info"))

    close_call(None)                       # trailing activity in the last turn
    if current_turn is not None:
        turns.append(current_turn)
    return turns


def ingest_codex_session(rollout_path, session_dir, captured_at):
    session_dir = Path(session_dir)
    derived = session_dir / "derived"
    events, malformed_lines = _read_events(rollout_path)

    meta = _session_meta(events)
    base_instructions = meta.get("base_instructions") or ""
    session_id = meta.get("session_id") or session_dir.name

    turns_raw = _segment_calls(events, base_instructions)

    turns = []
    requests_meta = []
    responses = 0
    req_index = 0
    for turn_index, turn in enumerate(turns_raw):
        turn_requests = []
        for call in turn["calls"]:
            breakdown = build_codex_breakdown(call)
            breakdown_name = f"req-{req_index:03d}.breakdown.json"
            write_json(derived / breakdown_name, breakdown)
            if breakdown["response"]:
                responses += 1

            meta_entry = {
                "index": req_index,
                # Codex has no verbatim wire body — the breakdown is a reconstruction.
                "raw_request": None,
                "raw_response": None,
                "breakdown": f"derived/{breakdown_name}",
                # rollout is ordered, so ordering is authoritative, not inferred.
                "order_confidence": "authoritative",
                "is_sidechannel": False,
                "usage": breakdown["usage"],
                "totals": {
                    "system_chars": breakdown["totals"]["system_chars"],
                    "message_chars": breakdown["totals"]["message_chars"],
                    "tool_chars": (breakdown["totals"]["tool_description_chars"]
                                   + breakdown["totals"]["tool_schema_chars"]),
                },
            }
            requests_meta.append(meta_entry)
            turn_requests.append(meta_entry)
            req_index += 1

        turns.append({
            "index": turn_index,
            "user_message_preview": turn["user"][:120].replace("\n", " "),
            "requests": turn_requests,
        })

    # Honest surfacing of the reconstruction's fidelity gap (user story 18): each
    # call's L3 is that call's own activity, not a verbatim replay of the full prior
    # context. Full-context replay is unsafe until compaction is handled (ticket 05).
    ambiguities = []
    if requests_meta:
        ambiguities.append({
            "kind": "reconstruction", "file": None,
            "detail": ("L3 messages are each model call's own activity (new user "
                       "message, tool calls/results, agent text), not a verbatim "
                       "replay of the full prior context."),
        })
    # Count compactions straight from the event stream, so the disclosure is
    # authoritative even if a boundary marker had no call to attach to.
    total_compactions = sum(1 for event in events if event.get("type") == "compacted")
    if total_compactions:
        ambiguities.append({
            "kind": "compaction", "file": None,
            "detail": (f"History was compacted {total_compactions} time(s); the "
                       "boundary is flagged in each affected call's L3 and the "
                       "pre-compaction history is not reconstructed."),
        })

    # Multi-agent detection (ticket 06): single-agent path runs unchanged; a
    # multi-agent session is flagged, not reconstructed as if one agent.
    multi_agent = _is_multi_agent(events)
    if multi_agent:
        ambiguities.append({
            "kind": "multi_agent", "file": None,
            "detail": ("Multi-agent session (inter_agent_communication_metadata "
                       "present). The per-call context is reconstructed as a single "
                       "linear stream and does not attribute context to individual "
                       "agents; treat cross-agent boundaries as unreliable."),
        })

    session = {
        "session_id": session_id,
        "captured_at": captured_at,
        "launcher_argv": None,
        "model": _first_model(events),
        # Codex-only additive flag: present on every Codex session (False for
        # single-agent) so a consumer needn't infer it from absence. It is NOT added
        # to the shared REQUIRED_SESSION_KEYS — that would break Claude sessions,
        # which don't carry it. Contract-level visibility rides on the ambiguities
        # note (a required key); this boolean is the convenient branch point.
        "multi_agent": multi_agent,
        "counts": {"turns": len(turns), "requests": len(requests_meta),
                   "responses": responses, "sidechannel": 0},
        "turns": turns,
        "sidechannel": [],
        "ambiguities": ambiguities,
        # Traceable ingest accounting: what was parsed vs. skipped. Additive and
        # backward-compatible — the contract validator ignores extra keys.
        "ingest": _event_accounting(events, malformed_lines),
    }

    problems = validate_session(session)
    session["ambiguities"].extend(
        {"kind": "schema", "file": None, "detail": problem} for problem in problems)
    write_json(session_dir / "session.json", session)
    return session

"""Ingest a Codex CLI rollout log into the frozen on-disk contract.

Codex writes each session as `~/.codex/sessions/<Y>/<M>/<D>/rollout-*.jsonl` — a
linear, ordered event stream. This module replays that stream and reconstructs a
per-model-call view, then maps it into the SAME `session.json` / breakdown shape
the Claude side produces, so the macOS app renders Codex sessions unchanged.

Skeleton scope (ticket 01): session_meta -> base instructions; each
`event_msg.user_message` starts a turn; following `event_msg.agent_message`s are
that turn's response; one request (model call) per turn. Later tickets add real
rollouts, richer turn segmentation, the full breakdown, compaction, and multi-agent.
"""
import json
from collections import Counter
from pathlib import Path

from .contract import write_json, validate_session
from .codex_breakdown import build_codex_breakdown

# Event kinds the current reconstruction actually consumes. Every other kind seen
# in a rollout is counted as skipped (see _event_accounting) so real-rollout
# surprises surface in the contract instead of being silently dropped. Later
# tickets consume more kinds (usage, tool calls, compaction) and move them out.
_CONSUMED_EVENT_KINDS = frozenset({
    "session_meta",
    "turn_context",
    "event_msg.user_message",
    "event_msg.agent_message",
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


def _segment_turns(events):
    """Skeleton segmentation: a user_message opens a turn; agent_messages until the
    next user_message are its response. Returns a list of {"user", "agent": [...]}."""
    turns = []
    current = None
    for event in events:
        if event.get("type") != "event_msg":
            continue
        payload = _payload(event)
        kind = payload.get("type")
        if kind == "user_message":
            if current is not None:
                turns.append(current)
            current = {"user": payload.get("message") or "", "agent": []}
        elif kind == "agent_message" and current is not None:
            current["agent"].append(payload.get("message") or "")
    if current is not None:
        turns.append(current)
    return turns


def ingest_codex_session(rollout_path, session_dir, captured_at):
    session_dir = Path(session_dir)
    derived = session_dir / "derived"
    events, malformed_lines = _read_events(rollout_path)

    meta = _session_meta(events)
    base_instructions = meta.get("base_instructions") or ""
    session_id = meta.get("session_id") or session_dir.name

    turns_raw = _segment_turns(events)

    turns = []
    requests_meta = []
    responses = 0
    for index, turn in enumerate(turns_raw):
        sent = [{"role": "user", "text": turn["user"]}]
        response = [{"role": "assistant", "text": text} for text in turn["agent"]]
        if response:
            responses += 1

        breakdown = build_codex_breakdown(base_instructions, sent, response)
        breakdown_name = f"req-{index:03d}.breakdown.json"
        write_json(derived / breakdown_name, breakdown)

        meta_entry = {
            "index": index,
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
        turns.append({
            "index": index,
            "user_message_preview": turn["user"][:120].replace("\n", " "),
            "requests": [meta_entry],
        })

    session = {
        "session_id": session_id,
        "captured_at": captured_at,
        "launcher_argv": None,
        "model": _first_model(events),
        "counts": {"turns": len(turns), "requests": len(requests_meta),
                   "responses": responses, "sidechannel": 0},
        "turns": turns,
        "sidechannel": [],
        "ambiguities": [],
        # Traceable ingest accounting: what was parsed vs. skipped. Additive and
        # backward-compatible — the contract validator ignores extra keys.
        "ingest": _event_accounting(events, malformed_lines),
    }

    problems = validate_session(session)
    session["ambiguities"].extend(
        {"kind": "schema", "file": None, "detail": problem} for problem in problems)
    write_json(session_dir / "session.json", session)
    return session

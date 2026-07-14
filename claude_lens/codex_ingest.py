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
from pathlib import Path

from .contract import write_json, validate_session
from .codex_breakdown import build_codex_breakdown


def _read_events(rollout_path):
    events = []
    with Path(rollout_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def _session_meta(events):
    for event in events:
        if event.get("type") == "session_meta":
            return event.get("payload", {}) or {}
    return {}


def _first_model(events):
    for event in events:
        if event.get("type") == "turn_context":
            model = (event.get("payload", {}) or {}).get("model")
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
        payload = event.get("payload", {}) or {}
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
    events = _read_events(rollout_path)

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
    }

    problems = validate_session(session)
    session["ambiguities"].extend(
        {"kind": "schema", "file": None, "detail": problem} for problem in problems)
    write_json(session_dir / "session.json", session)
    return session

from pathlib import Path

from .contract import read_json, write_json, validate_session
from .breakdown import build_breakdown
from .linking import link_requests
from .turns import segment_turns


def ingest_session(session_dir, captured_at, launcher_argv):
    session_dir = Path(session_dir)
    raw = session_dir / "raw"
    derived = session_dir / "derived"

    linked = link_requests(raw)
    ordered = linked["ordered"]
    request_bodies = [read_json(raw / item["request_file"]) for item in ordered]

    requests_meta = []
    for index, item in enumerate(ordered):
        response_body = None
        if item["inferred_response_file"]:
            response_body = read_json(raw / item["inferred_response_file"])
        bd = build_breakdown(request_bodies[index], response_body)
        bd_name = f"req-{index:03d}.breakdown.json"
        write_json(derived / bd_name, bd)
        requests_meta.append({
            "index": index,
            "raw_request": f"raw/{item['request_file']}",
            "raw_response": f"raw/{item['inferred_response_file']}" if item["inferred_response_file"] else None,
            "breakdown": f"derived/{bd_name}",
            "previous_message_id": item["previous_message_id"],
            "order_confidence": item["order_confidence"],
            "usage": bd["usage"],
            "totals": {
                "system_chars": bd["totals"]["system_chars"],
                "message_chars": bd["totals"]["message_chars"],
                "tool_chars": bd["totals"]["tool_description_chars"] + bd["totals"]["tool_schema_chars"],
            },
        })

    turns = segment_turns(request_bodies)
    for turn in turns:
        turn["requests"] = [requests_meta[i] for i in turn.pop("request_indices")]

    session = {
        "session_id": session_dir.name,
        "captured_at": captured_at,
        "launcher_argv": launcher_argv,
        "model": request_bodies[0].get("model") if request_bodies else None,
        "counts": {"turns": len(turns), "requests": len(ordered), "responses": len(linked["responses"])},
        "turns": turns,
        "ambiguities": linked["ambiguities"],
    }

    problems = validate_session(session)
    session["ambiguities"].extend({"reason": "schema", "detail": p} for p in problems)
    write_json(session_dir / "session.json", session)
    return session

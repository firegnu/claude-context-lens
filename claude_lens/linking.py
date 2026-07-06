from pathlib import Path

from .contract import read_json


def _previous_message_id(body):
    return body.get("diagnostics", {}).get("previous_message_id")


def _load_responses(raw_dir):
    responses = {}
    files = []
    for path in sorted(raw_dir.glob("*.response.json")):
        try:
            body = read_json(path)
        except (ValueError, OSError):
            files.append({"file": path.name, "corrupt": True})
            continue
        item = {"file": path.name, "mtime_ns": path.stat().st_mtime_ns,
                "id": body.get("id"), "stop_reason": body.get("stop_reason")}
        files.append(item)
        if item["id"]:
            responses[item["id"]] = item
    return responses, files


def _load_requests(raw_dir, responses):
    requests = []
    corrupt = []
    for path in sorted(raw_dir.glob("*.request.json")):
        try:
            body = read_json(path)
        except (ValueError, OSError):
            corrupt.append(path.name)
            continue
        prev = _previous_message_id(body)
        requests.append({
            "request_file": path.name,
            "mtime_ns": path.stat().st_mtime_ns,
            "messages_count": len(body.get("messages", [])),
            "previous_message_id": prev,
            "previous_response_file": responses.get(prev, {}).get("file"),
        })
    return requests, corrupt


def _sort_key(item):
    prev_rank = 0 if item["previous_message_id"] is None else 1
    return (item["messages_count"], prev_rank, item["mtime_ns"], item["request_file"])


def _confidence(item, index):
    if index == 0 and item["previous_message_id"] is None:
        return "high:start"
    if item["previous_message_id"] and item["previous_response_file"]:
        return "high:linked"
    if item["previous_message_id"] is None:
        return "medium:null-prev"
    return "low:missing-prev-response"


def link_requests(raw_dir):
    raw_dir = Path(raw_dir)
    responses, response_files = _load_responses(raw_dir)
    requests, corrupt_requests = _load_requests(raw_dir, responses)
    ordered = sorted(requests, key=_sort_key)

    for index, item in enumerate(ordered):
        item["index"] = index
        item["order_confidence"] = _confidence(item, index)

    for index, item in enumerate(ordered):
        nxt = ordered[index + 1] if index + 1 < len(ordered) else None
        response_id = nxt["previous_message_id"] if nxt else None
        item["inferred_response_file"] = responses.get(response_id, {}).get("file")

    used = {item.get("inferred_response_file") for item in ordered}
    leftover = [r for r in response_files if r.get("id") and r["file"] not in used]
    if ordered and ordered[-1]["inferred_response_file"] is None and leftover:
        ordered[-1]["inferred_response_file"] = max(leftover, key=lambda r: r["mtime_ns"])["file"]

    ambiguities = [
        {"kind": "order", "file": item["request_file"], "detail": item["order_confidence"]}
        for item in ordered if item["order_confidence"].startswith(("medium", "low"))
    ]
    ambiguities.extend({"kind": "corrupt-request", "file": name, "detail": None} for name in corrupt_requests)
    ambiguities.extend(
        {"kind": "corrupt-response", "file": r["file"], "detail": None}
        for r in response_files if r.get("corrupt")
    )

    valid_responses = [r for r in response_files if not r.get("corrupt")]
    return {"ordered": ordered, "responses": valid_responses, "ambiguities": ambiguities}

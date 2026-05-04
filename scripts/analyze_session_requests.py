#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def path_string(path):
    return str(path.absolute())


def previous_message_id(request_body):
    return request_body.get("diagnostics", {}).get("previous_message_id")


def load_responses(session_dir):
    responses = {}
    response_files = []
    for path in sorted(session_dir.glob("*.response.json")):
        body = read_json(path)
        item = {
            "file": path.name,
            "path": path_string(path),
            "mtime_ns": path.stat().st_mtime_ns,
            "id": body.get("id"),
            "model": body.get("model"),
            "stop_reason": body.get("stop_reason"),
            "content_blocks": len(body.get("content", [])),
        }
        response_files.append(item)
        if item["id"]:
            responses[item["id"]] = item
    return responses, response_files


def load_requests(session_dir, responses):
    requests = []
    for path in sorted(session_dir.glob("*.request.json")):
        body = read_json(path)
        prev_id = previous_message_id(body)
        prev_response = responses.get(prev_id)
        requests.append(
            {
                "request_file": path.name,
                "request_path": path_string(path),
                "mtime_ns": path.stat().st_mtime_ns,
                "model": body.get("model"),
                "messages_count": len(body.get("messages", [])),
                "tools_count": len(body.get("tools", [])),
                "previous_message_id": prev_id,
                "previous_response_file": prev_response["file"] if prev_response else None,
                "previous_response_stop_reason": prev_response["stop_reason"] if prev_response else None,
            }
        )
    return requests


def request_sort_key(item):
    prev_rank = 0 if item["previous_message_id"] is None else 1
    return (item["messages_count"], prev_rank, item["mtime_ns"], item["request_file"])


def confidence(item, index):
    if index == 0 and item["previous_message_id"] is None:
        return "high:start"
    if item["previous_message_id"] and item["previous_response_file"]:
        return "high:linked"
    if item["previous_message_id"] is None:
        return "medium:null-prev"
    return "low:missing-prev-response"


def add_response_to_next_links(ordered, responses):
    for index, item in enumerate(ordered):
        next_item = ordered[index + 1] if index + 1 < len(ordered) else None
        response_id = next_item["previous_message_id"] if next_item else None
        response = responses.get(response_id)
        item["inferred_response_file"] = response["file"] if response else None
        item["inferred_response_id"] = response_id if response else None
        item["inferred_response_stop_reason"] = response["stop_reason"] if response else None
        if next_item and response:
            item["inferred_response_basis"] = "next_request.previous_message_id"
        elif next_item and next_item["previous_message_id"] is None:
            item["inferred_response_basis"] = "none:next_request_has_null_previous_message_id"
        else:
            item["inferred_response_basis"] = "none:no_next_request"


def build_ambiguities(ordered):
    ambiguities = []
    seen_counts = {}
    for item in ordered:
        seen_counts.setdefault(item["messages_count"], []).append(item["request_file"])
        if item["confidence"].startswith("medium") or item["confidence"].startswith("low"):
            ambiguities.append(
                {
                    "request_file": item["request_file"],
                    "reason": item["confidence"],
                    "messages_count": item["messages_count"],
                    "previous_message_id": item["previous_message_id"],
                }
            )
    for count, files in seen_counts.items():
        if len(files) > 1:
            ambiguities.append({"reason": "duplicate_messages_count", "messages_count": count, "request_files": files})
    return ambiguities


def timeline_markdown(manifest):
    lines = [
        "# Session Request Timeline",
        "",
        f"- session_dir: `{manifest['session_dir']}`",
        f"- request_count: `{manifest['counts']['requests']}`",
        f"- response_count: `{manifest['counts']['responses']}`",
        "",
        "| idx | messages | confidence | request | previous response | inferred response |",
        "|---:|---:|---|---|---|---|",
    ]
    for item in manifest["ordered_requests"]:
        lines.append(
            "| {idx} | {messages} | `{confidence}` | `{request}` | `{prev}` | `{response}` |".format(
                idx=item["index"],
                messages=item["messages_count"],
                confidence=item["confidence"],
                request=item["request_file"],
                prev=item["previous_response_file"] or "-",
                response=item["inferred_response_file"] or "-",
            )
        )
    if manifest["ambiguities"]:
        lines.extend(["", "## Ambiguities", ""])
        for item in manifest["ambiguities"]:
            lines.append(f"- `{item['reason']}`: {json.dumps(item, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def analyze(session_dir, out_dir):
    responses, response_files = load_responses(session_dir)
    ordered = sorted(load_requests(session_dir, responses), key=request_sort_key)
    for index, item in enumerate(ordered, 1):
        item["index"] = index
        item["confidence"] = confidence(item, index - 1)
    add_response_to_next_links(ordered, responses)
    manifest = {
        "session_dir": path_string(session_dir),
        "counts": {"requests": len(ordered), "responses": len(response_files)},
        "ordering_strategy": [
            "messages_count ascending",
            "null previous_message_id before linked requests at the same message count",
            "mtime_ns as a tie-breaker",
            "previous_message_id to response.id for link confidence",
        ],
        "ordered_requests": ordered,
        "responses": sorted(response_files, key=lambda item: item["mtime_ns"]),
        "ambiguities": build_ambiguities(ordered),
    }
    write_json(out_dir / "session_manifest.json", manifest)
    write_text(out_dir / "timeline.md", timeline_markdown(manifest))
    print(f"Wrote session request analysis to {out_dir}")


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze logical request order for a Claude Code raw bodies directory.")
    parser.add_argument("--session-dir", type=Path, required=True, help="Directory containing *.request.json files.")
    parser.add_argument("--out", type=Path, help="Output directory. Defaults to <session-dir>/session_request_order.")
    return parser.parse_args()


def main():
    args = parse_args()
    out_dir = args.out or (args.session_dir / "session_request_order")
    analyze(args.session_dir, out_dir)


if __name__ == "__main__":
    main()

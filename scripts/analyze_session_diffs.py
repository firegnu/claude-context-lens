#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path


CONFIG_KEYS = [
    "model",
    "max_tokens",
    "stream",
    "thinking",
    "betas",
    "context_management",
    "output_config",
]


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def stable_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def preview(text, size=180):
    return text.replace("\n", "\\n")[:size]


def text_from_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def content_blocks(content):
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def collect_ids(blocks, block_type, key):
    values = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == block_type and block.get(key):
            values.append(block[key])
    return values


def message_summary(message, index):
    blocks = content_blocks(message.get("content"))
    text = text_from_content(message.get("content"))
    return {
        "index": index,
        "role": message.get("role"),
        "hash": digest(message),
        "content_block_count": len(blocks),
        "content_types": [block.get("type") for block in blocks if isinstance(block, dict)],
        "text_chars": len(text),
        "preview": preview(text),
        "tool_use_ids": collect_ids(blocks, "tool_use", "id"),
        "tool_result_ids": collect_ids(blocks, "tool_result", "tool_use_id"),
    }


def request_config(body):
    return {key: body.get(key) for key in CONFIG_KEYS}


def changed_indexes(previous, current):
    limit = max(len(previous), len(current))
    indexes = []
    for index in range(limit):
        old = previous[index] if index < len(previous) else None
        new = current[index] if index < len(current) else None
        if digest(old) != digest(new):
            indexes.append(index)
    return indexes


def tools_by_name(tools):
    result = {}
    for index, tool in enumerate(tools):
        name = tool.get("name", f"tool_{index}") if isinstance(tool, dict) else f"tool_{index}"
        result[name] = digest(tool)
    return result


def diff_tools(previous, current):
    old = tools_by_name(previous)
    new = tools_by_name(current)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(name for name in set(old) & set(new) if old[name] != new[name])
    return {"changed": bool(added or removed or changed), "added": added, "removed": removed, "changed_names": changed}


def common_prefix_count(previous_messages, current_messages):
    count = 0
    for old, new in zip(previous_messages, current_messages):
        if digest(old) != digest(new):
            break
        count += 1
    return count


def diff_messages(previous_messages, current_messages):
    prefix = common_prefix_count(previous_messages, current_messages)
    previous_tail = previous_messages[prefix:]
    current_tail = current_messages[prefix:]
    append_only = prefix == len(previous_messages) and len(current_messages) >= len(previous_messages)
    return {
        "previous_count": len(previous_messages),
        "current_count": len(current_messages),
        "common_prefix_count": prefix,
        "append_only": append_only,
        "added_count": len(current_tail),
        "removed_or_rewritten_count": len(previous_tail),
        "reset_or_rewrite_suspected": not append_only and bool(previous_messages),
        "added": [message_summary(message, prefix + offset) for offset, message in enumerate(current_tail)],
        "removed_or_rewritten": [message_summary(message, prefix + offset) for offset, message in enumerate(previous_tail)],
    }


def response_summary(session_dir, file_name):
    if not file_name:
        return None
    path = session_dir / file_name
    if not path.exists():
        return {"file": file_name, "missing": True}
    body = read_json(path)
    blocks = content_blocks(body.get("content"))
    return {
        "file": file_name,
        "id": body.get("id"),
        "stop_reason": body.get("stop_reason"),
        "content_block_count": len(blocks),
        "content_types": [block.get("type") for block in blocks if isinstance(block, dict)],
        "usage": body.get("usage"),
    }


def turn_diff(session_dir, order_item, previous_body, current_body):
    previous_body = previous_body or {}
    has_previous = bool(previous_body)
    system = current_body.get("system", [])
    old_system = previous_body.get("system", [])
    tools = current_body.get("tools", [])
    old_tools = previous_body.get("tools", [])
    config = request_config(current_body)
    old_config = request_config(previous_body) if previous_body else None
    messages = diff_messages(previous_body.get("messages", []), current_body.get("messages", []))
    return {
        "index": order_item["index"],
        "request_file": order_item["request_file"],
        "previous_request_file": order_item.get("previous_request_file"),
        "confidence": order_item.get("confidence"),
        "response": response_summary(session_dir, order_item.get("inferred_response_file")),
        "config": {"changed": has_previous and old_config is not None and digest(old_config) != digest(config), "hash": digest(config)},
        "system": {"changed": has_previous and digest(old_system) != digest(system), "count": len(system), "changed_indexes": changed_indexes(old_system, system) if has_previous else []},
        "tools": {"count": len(tools), **(diff_tools(old_tools, tools) if has_previous else {"changed": False, "added": [], "removed": [], "changed_names": []})},
        "messages": messages,
    }


def timeline_markdown(manifest):
    lines = [
        "# Session Request Diffs",
        "",
        f"- session_dir: `{manifest['session_dir']}`",
        f"- turns: `{len(manifest['turn_diffs'])}`",
        "",
        "| turn | messages | prefix | added | rewritten | system | tools | request |",
        "|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for item in manifest["turn_diffs"]:
        messages = item["messages"]
        lines.append(
            "| {turn} | {prev}->{curr} | {prefix} | {added} | {rewritten} | {system} | {tools} | `{request}` |".format(
                turn=item["index"],
                prev=messages["previous_count"],
                curr=messages["current_count"],
                prefix=messages["common_prefix_count"],
                added=messages["added_count"],
                rewritten=messages["removed_or_rewritten_count"],
                system="changed" if item["system"]["changed"] else "same",
                tools="changed" if item["tools"]["changed"] else "same",
                request=item["request_file"],
            )
        )
        for added in messages["added"][:4]:
            lines.append(f"  - added message[{added['index']}] `{added['role']}` `{added['content_types']}` {added['preview']}")
        if messages["added_count"] > 4:
            lines.append(f"  - ... {messages['added_count'] - 4} more added messages")
    return "\n".join(lines) + "\n"


def analyze(session_dir, order_path, out_dir):
    order = read_json(order_path)
    turn_diffs = []
    previous_body = None
    previous_file = None
    for item in order.get("ordered_requests", []):
        request_file = item["request_file"]
        current_body = read_json(session_dir / request_file)
        enriched_item = dict(item)
        enriched_item["previous_request_file"] = previous_file
        diff = turn_diff(session_dir, enriched_item, previous_body, current_body)
        turn_diffs.append(diff)
        write_json(out_dir / "turns" / f"{item['index']:04d}.json", diff)
        previous_body = current_body
        previous_file = request_file
    manifest = {
        "session_dir": str(session_dir.absolute()),
        "order_file": str(order_path.absolute()),
        "turn_diffs": turn_diffs,
    }
    write_json(out_dir / "session_diff_manifest.json", manifest)
    write_text(out_dir / "timeline_diff.md", timeline_markdown(manifest))
    print(f"Wrote session diffs to {out_dir}")


def parse_args():
    parser = argparse.ArgumentParser(description="Diff logically ordered Claude Code request bodies within one session.")
    parser.add_argument("--session-dir", type=Path, required=True, help="Directory containing raw *.request.json files.")
    parser.add_argument("--order", type=Path, required=True, help="session_manifest.json from analyze_session_requests.py.")
    parser.add_argument("--out", type=Path, help="Output directory. Defaults to <session-dir>/session_diffs.")
    return parser.parse_args()


def main():
    args = parse_args()
    out_dir = args.out or (args.session_dir / "session_diffs")
    analyze(args.session_dir, args.order, out_dir)


if __name__ == "__main__":
    main()

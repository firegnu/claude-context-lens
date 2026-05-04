#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
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
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def stable_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def strip_ephemeral(value):
    if isinstance(value, dict):
        return {key: strip_ephemeral(item) for key, item in value.items() if key != "cache_control"}
    if isinstance(value, list):
        return [strip_ephemeral(item) for item in value]
    return value


def normalize_content_for_compare(content):
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [strip_ephemeral(block) for block in content]
    return content


def normalize_message_for_compare(value):
    if isinstance(value, dict) and "role" in value and "content" in value:
        result = strip_ephemeral(value)
        result["content"] = normalize_content_for_compare(value.get("content"))
        return result
    return strip_ephemeral(value)


def semantic_digest(value):
    return digest(normalize_message_for_compare(value))


def preview(text, size=180):
    return ANSI_RE.sub("", text).replace("\n", "\\n")[:size]


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


def block_preview(block):
    if not isinstance(block, dict):
        return ""
    block_type = block.get("type")
    if block_type == "text":
        return block.get("text", "")
    if block_type == "tool_use":
        tool_input = block.get("input", {})
        return f"{block.get('name', '<tool>')} {stable_json(tool_input)}"
    if block_type == "tool_result":
        content = block.get("content", "")
        return content if isinstance(content, str) else stable_json(content)
    return ""


def content_preview(blocks, fallback_text):
    parts = [block_preview(block) for block in blocks]
    text = "\n".join(part for part in parts if part)
    return preview(text or fallback_text)


def message_summary(message, index):
    blocks = content_blocks(message.get("content"))
    text = text_from_content(message.get("content"))
    return {
        "index": index,
        "role": message.get("role"),
        "hash": digest(message),
        "semantic_hash": semantic_digest(message),
        "content_block_count": len(blocks),
        "content_types": [block.get("type") for block in blocks if isinstance(block, dict)],
        "text_chars": len(text),
        "preview": content_preview(blocks, text),
        "tool_use_ids": collect_ids(blocks, "tool_use", "id"),
        "tool_names": collect_ids(blocks, "tool_use", "name"),
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


def common_prefix_count(previous_messages, current_messages, digest_func=semantic_digest):
    count = 0
    for old, new in zip(previous_messages, current_messages):
        if digest_func(old) != digest_func(new):
            break
        count += 1
    return count


def diff_messages(previous_messages, current_messages):
    prefix = common_prefix_count(previous_messages, current_messages)
    raw_prefix = common_prefix_count(previous_messages, current_messages, digest)
    previous_tail = previous_messages[prefix:]
    current_tail = current_messages[prefix:]
    append_only = prefix == len(previous_messages) and len(current_messages) >= len(previous_messages)
    metadata_only_indexes = [
        index
        for index in range(prefix)
        if digest(previous_messages[index]) != digest(current_messages[index])
    ]
    return {
        "previous_count": len(previous_messages),
        "current_count": len(current_messages),
        "common_prefix_count": prefix,
        "raw_common_prefix_count": raw_prefix,
        "append_only": append_only,
        "added_count": len(current_tail),
        "removed_or_rewritten_count": len(previous_tail),
        "metadata_only_changed_indexes": metadata_only_indexes,
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


def describe_added_message(summary):
    content_types = summary["content_types"]
    label = f"message[{summary['index']}] {summary['role']} {content_types}"
    if "tool_use" in content_types and summary["tool_names"]:
        label += f" -> call {', '.join(summary['tool_names'])}"
    if "tool_result" in content_types and summary["tool_result_ids"]:
        label += f" -> result for {', '.join(summary['tool_result_ids'])}"
    if summary["preview"]:
        label += f": {summary['preview']}"
    return label


def describe_message_flow(item):
    messages = item["messages"]
    added = messages["added"]
    if messages["previous_count"] == 0:
        return "初始化 context：放入第一批 messages。"
    if messages["append_only"]:
        if len(added) == 2 and added[0]["role"] == "assistant" and added[1]["role"] == "user":
            first_types = added[0]["content_types"]
            second_types = added[1]["content_types"]
            if "tool_use" in first_types and "tool_result" in second_types:
                tool = ", ".join(added[0]["tool_names"]) or "tool"
                return f"工具循环推进：追加 assistant 调用 {tool}，再追加对应 tool_result。"
        if added and added[-1]["role"] == "user" and "text" in added[-1]["content_types"]:
            return "用户发出新消息：当前 request 在历史后追加了新的 user text。"
        return "纯追加：当前 request 保留上一轮语义内容，并在尾部追加新 messages。"
    if messages["metadata_only_changed_indexes"] and not messages["removed_or_rewritten"]:
        count = len(messages["metadata_only_changed_indexes"])
        return f"仅元数据变化：{count} 条 message 的 cache_control 等字段变化，语义内容不变。"
    return "非纯追加：从 common_prefix 后开始出现语义替换、裁剪或分支变化。"


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
        "阅读顺序：先看 `meaning`，再看 `messages` 的计数。`prefix` 表示两轮从头开始语义相同的 message 数；`meta` 表示只有 `cache_control` 这类元数据变了。",
        "",
        "| turn | meaning | messages | prefix | add | rewrite | meta | system | tools | request |",
        "|---:|---|---:|---:|---:|---:|---|---|---|---|",
    ]
    for item in manifest["turn_diffs"]:
        messages = item["messages"]
        lines.append(
            "| {turn} | {meaning} | {prev}->{curr} | {prefix} | {added} | {rewritten} | {meta} | {system} | {tools} | `{request}` |".format(
                turn=item["index"],
                meaning=describe_message_flow(item),
                prev=messages["previous_count"],
                curr=messages["current_count"],
                prefix=messages["common_prefix_count"],
                added=messages["added_count"],
                rewritten=messages["removed_or_rewritten_count"],
                meta=str(len(messages["metadata_only_changed_indexes"])) if messages["metadata_only_changed_indexes"] else "-",
                system="changed" if item["system"]["changed"] else "same",
                tools="changed" if item["tools"]["changed"] else "same",
                request=item["request_file"],
            )
        )
        for added in messages["added"][:4]:
            lines.append(f"  - {describe_added_message(added)}")
        if messages["added_count"] > 4:
            lines.append(f"  - ... {messages['added_count'] - 4} more added messages")
    return "\n".join(lines) + "\n"


def event_base(item, event, summary=None):
    result = {
        "turn": item["index"],
        "event": event,
        "request_file": item["request_file"],
    }
    if summary:
        result.update(
            {
                "message_index": summary["index"],
                "role": summary["role"],
                "content_types": summary["content_types"],
                "preview": summary["preview"],
            }
        )
    return result


def event_for_added_message(item, summary):
    content_types = summary["content_types"]
    if "tool_use" in content_types:
        event = event_base(item, "tool_use", summary)
        event["tool"] = summary["tool_names"][0] if summary["tool_names"] else None
        event["tool_use_ids"] = summary["tool_use_ids"]
        return event
    if "tool_result" in content_types:
        event = event_base(item, "tool_result", summary)
        event["tool_use_id"] = summary["tool_result_ids"][0] if summary["tool_result_ids"] else None
        return event
    if summary["role"] == "user" and "text" in content_types:
        return event_base(item, "user_text", summary)
    if summary["role"] == "assistant" and "text" in content_types:
        return event_base(item, "assistant_text", summary)
    return event_base(item, "message_added", summary)


def events_for_turn(item):
    events = []
    if item["config"]["changed"]:
        events.append(event_base(item, "config_changed"))
    if item["system"]["changed"]:
        event = event_base(item, "system_changed")
        event["changed_indexes"] = item["system"]["changed_indexes"]
        events.append(event)
    if item["tools"]["changed"]:
        event = event_base(item, "tools_changed")
        event["added"] = item["tools"]["added"]
        event["removed"] = item["tools"]["removed"]
        event["changed_names"] = item["tools"]["changed_names"]
        events.append(event)
    if item["messages"]["metadata_only_changed_indexes"]:
        event = event_base(item, "metadata_only_changed")
        event["message_indexes"] = item["messages"]["metadata_only_changed_indexes"]
        events.append(event)
    for summary in item["messages"]["removed_or_rewritten"]:
        events.append(event_base(item, "message_removed_or_rewritten", summary))
    for summary in item["messages"]["added"]:
        events.append(event_for_added_message(item, summary))
    return events


def response_line(response):
    if not response:
        return "- Response: not inferred"
    if response.get("missing"):
        return f"- Response: missing `{response['file']}`"
    return "- Response: `{file}`, stop_reason `{stop}`, content {types}".format(
        file=response["file"],
        stop=response["stop_reason"],
        types=response["content_types"],
    )


def stability_lines(item):
    messages = item["messages"]
    return [
        "- Stable context: system {system}, tools {tools}, config {config}".format(
            system="changed" if item["system"]["changed"] else "same",
            tools="changed" if item["tools"]["changed"] else "same",
            config="changed" if item["config"]["changed"] else "same",
        ),
        "- Message shape: {prev}->{curr}, prefix {prefix}, add {added}, rewrite {rewrite}, meta {meta}".format(
            prev=messages["previous_count"],
            curr=messages["current_count"],
            prefix=messages["common_prefix_count"],
            added=messages["added_count"],
            rewrite=messages["removed_or_rewritten_count"],
            meta=len(messages["metadata_only_changed_indexes"]),
        ),
    ]


def turn_story_markdown(item):
    lines = [
        f"# Turn {item['index']:04d}",
        "",
        f"- Request: `{item['request_file']}`",
        f"- Previous request: `{item['previous_request_file'] or '<none>'}`",
        f"- What happened: {describe_message_flow(item)}",
        response_line(item["response"]),
        *stability_lines(item),
        "",
        "## Context Added",
    ]
    added = item["messages"]["added"]
    if added:
        lines.extend(f"- {describe_added_message(summary)}" for summary in added)
    else:
        lines.append("- None")
    if item["messages"]["removed_or_rewritten"]:
        lines.extend(["", "## Removed Or Rewritten"])
        lines.extend(f"- {describe_added_message(summary)}" for summary in item["messages"]["removed_or_rewritten"])
    events = events_for_turn(item)
    lines.extend(["", "## Events"])
    if events:
        for event in events:
            label = event["event"]
            detail = event.get("tool") or event.get("tool_use_id") or event.get("preview") or ""
            lines.append(f"- `{label}` {preview(str(detail), 140)}".rstrip())
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def session_story_markdown(manifest):
    lines = [
        "# Session Story",
        "",
        f"- session_dir: `{manifest['session_dir']}`",
        f"- turns: `{len(manifest['turn_diffs'])}`",
        "",
        "这个文件按 agent loop 讲述每一轮比上一轮多了什么。需要底层字段时，再回看 `timeline_diff.md` 或 `turns/*.json`。",
    ]
    for item in manifest["turn_diffs"]:
        lines.extend(
            [
                "",
                f"## Step {item['index']:04d}",
                "",
                f"- {describe_message_flow(item)}",
                f"- Request: `{item['request_file']}`",
                response_line(item["response"]),
                *stability_lines(item),
            ]
        )
        added = item["messages"]["added"]
        if added:
            lines.append("- Context added:")
            lines.extend(f"  - {describe_added_message(summary)}" for summary in added[:3])
            if len(added) > 3:
                lines.append(f"  - ... {len(added) - 3} more")
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
        write_text(out_dir / "turns" / f"{item['index']:04d}.md", turn_story_markdown(diff))
        previous_body = current_body
        previous_file = request_file
    manifest = {
        "session_dir": str(session_dir.absolute()),
        "order_file": str(order_path.absolute()),
        "turn_diffs": turn_diffs,
    }
    write_json(out_dir / "session_diff_manifest.json", manifest)
    write_text(out_dir / "timeline_diff.md", timeline_markdown(manifest))
    write_text(out_dir / "session_story.md", session_story_markdown(manifest))
    write_jsonl(out_dir / "events.jsonl", [event for item in turn_diffs for event in events_for_turn(item)])
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

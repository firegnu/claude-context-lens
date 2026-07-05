import json
import re

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

CONFIG_KEYS = [
    "model", "max_tokens", "stream", "thinking", "betas",
    "context_management", "output_config", "metadata", "diagnostics",
]


def clean_text(text):
    return ANSI_RE.sub("", text)


def text_of(block):
    if isinstance(block, str):
        return clean_text(block)
    block_type = block.get("type")
    if block_type == "text":
        return block.get("text", "")
    if block_type == "tool_result":
        content = block.get("content", "")
        if isinstance(content, str):
            return clean_text(content)
        return json.dumps(content, ensure_ascii=False, indent=2)
    return json.dumps(block, ensure_ascii=False)


def block_meta(block):
    meta = {"type": block.get("type")}
    if block.get("type") == "tool_use":
        meta["tool_use_id"] = block.get("id")
        meta["tool_name"] = block.get("name")
    if block.get("type") == "tool_result":
        meta["tool_use_id"] = block.get("tool_use_id")
        meta["is_error"] = block.get("is_error")
    return meta


def build_breakdown(request_body, response_body):
    system = []
    for index, block in enumerate(request_body.get("system", [])):
        body = text_of(block)
        system.append({
            "index": index, "type": block.get("type"),
            "cache_control": block.get("cache_control"), "chars": len(body), "text": body,
        })

    messages = []
    for message_index, message in enumerate(request_body.get("messages", [])):
        content = message.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for content_index, block in enumerate(content):
            body = text_of(block)
            messages.append({
                "message_index": message_index, "content_index": content_index,
                "role": message.get("role"), **block_meta(block),
                "chars": len(body), "text": body,
            })

    tools = []
    for index, tool in enumerate(request_body.get("tools", [])):
        description = tool.get("description") or ""
        schema = tool.get("input_schema")
        tools.append({
            "index": index, "name": tool.get("name"),
            "description": tool.get("description"), "input_schema": schema,
            "description_chars": len(description),
            "schema_chars": len(json.dumps(schema, ensure_ascii=False)),
        })

    response = None
    usage = None
    if response_body:
        response = [
            {"index": i, "type": b.get("type"), "chars": len(text_of(b)), "text": text_of(b)}
            for i, b in enumerate(response_body.get("content", []))
        ]
        usage = response_body.get("usage")

    totals = {
        "system_chars": sum(s["chars"] for s in system),
        "message_chars": sum(m["chars"] for m in messages),
        "tool_description_chars": sum(t["description_chars"] for t in tools),
        "tool_schema_chars": sum(t["schema_chars"] for t in tools),
    }

    return {
        "request_config": {k: request_body.get(k) for k in CONFIG_KEYS},
        "system": system, "messages": messages, "tools": tools,
        "response": response, "usage": usage, "totals": totals,
    }

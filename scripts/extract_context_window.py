#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT / "9885e4e6-a4c1-4ced-ac0e-3371a9e13138.request.json"
RESPONSE = ROOT / "req_011Caggp8Nn13XNpRjzADwVM.response.json"
OUT = ROOT / "context_window_breakdown"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slug(text):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")
    return cleaned[:80] or "unnamed"


def clean_text(text):
    return ANSI_RE.sub("", text)


def text_of(block):
    block_type = block.get("type")
    if block_type == "text":
        return block.get("text", "")
    if block_type == "tool_result":
        content = block.get("content", "")
        if isinstance(content, str):
            return clean_text(content)
        return json.dumps(content, ensure_ascii=False, indent=2)
    return json.dumps(block, ensure_ascii=False)


def preview(text, size=160):
    return text[:size].replace("\n", "\\n")


def dump_markdown_block(path, title, meta, body):
    lines = [f"# {title}", ""]
    for key, value in meta.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "```text", body, "```", ""])
    write_text(path, "\n".join(lines))


def content_meta(block, source, role, index):
    meta = {
        "source": source,
        "role": role,
        "index": index,
        "type": block.get("type"),
    }
    if block.get("type") == "tool_use":
        meta["tool_use_id"] = block.get("id")
        meta["tool_name"] = block.get("name")
    if block.get("type") == "tool_result":
        meta["tool_use_id"] = block.get("tool_use_id")
        meta["is_error"] = block.get("is_error")
    return meta


def path_string(path):
    return str(path.absolute())


def request_config(request):
    return {
        key: request.get(key)
        for key in [
            "model",
            "max_tokens",
            "stream",
            "thinking",
            "betas",
            "context_management",
            "output_config",
            "metadata",
            "diagnostics",
        ]
    }


def response_manifest(response):
    if response is None:
        return None
    return {
        "id": response.get("id"),
        "model": response.get("model"),
        "stop_reason": response.get("stop_reason"),
        "usage": response.get("usage"),
        "content_blocks": [],
    }


def extract(request_path, response_path, out_path):
    request = read_json(request_path)
    response = read_json(response_path) if response_path else None
    manifest = {
        "source_files": {
            "request": path_string(request_path),
            "response": path_string(response_path) if response_path else None,
        },
        "request_config": request_config(request),
        "sections": [],
        "response": response_manifest(response),
    }

    write_json(out_path / "00_request_config.json", manifest["request_config"])

    for index, block in enumerate(request.get("system", [])):
        body = text_of(block)
        cache_control = block.get("cache_control")
        file_path = out_path / "01_system" / f"{index:02d}.md"
        dump_markdown_block(
            file_path,
            f"System Block {index}",
            {
                "source": "request.system",
                "index": index,
                "type": block.get("type"),
                "chars": len(body),
                "cache_control": json.dumps(cache_control, ensure_ascii=False),
            },
            body,
        )
        manifest["sections"].append(
            {
                "order": len(manifest["sections"]),
                "kind": "system",
                "index": index,
                "chars": len(body),
                "cache_control": cache_control,
                "file": path_string(file_path),
                "preview": preview(body),
            }
        )

    messages = request.get("messages", [])
    for message_index, message in enumerate(messages):
        for block_index, block in enumerate(message.get("content", [])):
            body = text_of(block)
            file_path = out_path / "02_messages" / f"message_{message_index:02d}_content_{block_index:02d}.md"
            dump_markdown_block(
                file_path,
                f"Message {message_index} Content Block {block_index}",
                {**content_meta(block, f"request.messages[{message_index}].content", message.get("role"), block_index), "chars": len(body)},
                body,
            )
            manifest["sections"].append(
                {
                    "order": len(manifest["sections"]),
                    "kind": "message_content",
                    "message_index": message_index,
                    "content_index": block_index,
                    "role": message.get("role"),
                    "chars": len(body),
                    "file": path_string(file_path),
                    "preview": preview(body),
                }
            )

    tools_summary = []
    for index, tool in enumerate(request.get("tools", [])):
        name = tool.get("name", f"tool_{index}")
        body = {
            "name": name,
            "description": tool.get("description"),
            "input_schema": tool.get("input_schema"),
        }
        file_path = out_path / "03_tools" / f"{index:02d}_{slug(name)}.json"
        write_json(file_path, body)
        item = {
            "order": len(manifest["sections"]),
            "kind": "tool",
            "index": index,
            "name": name,
            "description_chars": len(tool.get("description", "")),
            "schema_chars": len(json.dumps(tool.get("input_schema"), ensure_ascii=False)),
            "file": path_string(file_path),
        }
        manifest["sections"].append(item)
        tools_summary.append(item)
    write_json(out_path / "03_tools_summary.json", tools_summary)

    for index, block in enumerate(response.get("content", []) if response else []):
        body = text_of(block)
        file_path = out_path / "04_response" / f"content_{index:02d}.md"
        dump_markdown_block(
            file_path,
            f"Response Content Block {index}",
            {
                "source": "response.content",
                "index": index,
                "type": block.get("type"),
                "chars": len(body),
            },
            body,
        )
        manifest["response"]["content_blocks"].append(
            {
                "index": index,
                "chars": len(body),
                "file": path_string(file_path),
                "preview": preview(body),
            }
        )

    manifest["totals"] = {
        "system_chars": sum(item["chars"] for item in manifest["sections"] if item["kind"] == "system"),
        "message_content_chars": sum(item["chars"] for item in manifest["sections"] if item["kind"] == "message_content"),
        "tool_description_chars": sum(item["description_chars"] for item in tools_summary),
        "tool_schema_chars": sum(item["schema_chars"] for item in tools_summary),
    }
    write_json(out_path / "manifest.json", manifest)
    print(f"Wrote context window breakdown to {out_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Break one Claude Code request into context-window sections.")
    parser.add_argument("--request", type=Path, default=REQUEST, help="Path to a *.request.json file.")
    parser.add_argument("--response", type=Path, help="Optional path to a matching *.response.json file.")
    parser.add_argument("--out", type=Path, default=OUT, help="Output directory for the extracted files.")
    parser.add_argument("--no-response", action="store_true", help="Only extract the request; ignore response output.")
    return parser.parse_args()


def main():
    args = parse_args()
    response_path = None
    if not args.no_response:
        response_path = args.response
        if response_path is None and args.request.absolute() == REQUEST.absolute() and RESPONSE.exists():
            response_path = RESPONSE
    extract(args.request, response_path, args.out)


if __name__ == "__main__":
    main()

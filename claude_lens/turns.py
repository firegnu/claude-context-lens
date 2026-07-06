# Claude Code fires background requests (e.g. autocomplete "suggestions") that
# inject a marker prompt as the final user message. They use the same model as
# real turns, so the injected text is the only reliable signal.
SIDECHANNEL_MARKERS = ("[SUGGESTION MODE",)


def _is_real_user_message(message):
    if message.get("role") != "user":
        return False
    content = message.get("content", [])
    if isinstance(content, str):
        return True
    return any(isinstance(b, dict) and b.get("type") != "tool_result" for b in content)


def real_user_message_count(request_body):
    return sum(1 for m in request_body.get("messages", []) if _is_real_user_message(m))


def last_real_user_text(request_body):
    text = ""
    for message in request_body.get("messages", []):
        if not _is_real_user_message(message):
            continue
        content = message.get("content", [])
        if isinstance(content, str):
            text = content
            continue
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(p for p in parts if p)
    return text


def is_sidechannel(request_body):
    return last_real_user_text(request_body).lstrip().startswith(SIDECHANNEL_MARKERS)


def segment_turns(request_bodies):
    turns = []
    for index, body in enumerate(request_bodies):
        if is_sidechannel(body):
            continue
        turn_index = max(real_user_message_count(body) - 1, 0)
        if not turns or turns[-1]["index"] != turn_index:
            preview = last_real_user_text(body)[:120].replace("\n", " ")
            turns.append({"index": turn_index, "user_message_preview": preview, "request_indices": []})
        turns[-1]["request_indices"].append(index)
    return turns

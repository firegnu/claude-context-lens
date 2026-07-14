"""Break a single reconstructed Codex model call into the five contract layers.

Skeleton version (ticket 01): maps base instructions, the sent user messages,
and the agent response into L2/L3/L5. L1 config, L4 tools, reasoning placeholders,
and usage detail are filled out by later tickets (04). The output shape matches
what `contract.validate_breakdown` requires, so the macOS app renders it unchanged.
"""


def _message_entry(message_index, role, text):
    return {
        "message_index": message_index,
        "content_index": 0,
        "role": role,
        "type": "message",
        "chars": len(text),
        "text": text,
    }


def build_codex_breakdown(base_instructions, sent_messages, response_messages):
    """Assemble one call's five-layer breakdown.

    - base_instructions: L2 system base text (from session_meta).
    - sent_messages: list of {"role", "text"} that made up the request (L3).
    - response_messages: list of {"role", "text"} the model returned (L5), or None.

    L1 request_config and usage are empty here; ticket 04 fills them from
    turn_context and event_msg.token_count.
    """
    system = []
    if base_instructions:
        system.append({"index": 0, "type": "base_instructions",
                       "chars": len(base_instructions), "text": base_instructions})

    messages = [_message_entry(i, m["role"], m["text"])
                for i, m in enumerate(sent_messages)]

    response = None
    if response_messages:
        response = [{"index": i, "type": "message", "role": m["role"],
                     "chars": len(m["text"]), "text": m["text"]}
                    for i, m in enumerate(response_messages)]

    tools = []
    totals = {
        "system_chars": sum(s["chars"] for s in system),
        "message_chars": sum(m["chars"] for m in messages),
        "tool_description_chars": 0,
        "tool_schema_chars": 0,
    }

    return {
        "request_config": {},
        "system": system,
        "messages": messages,
        "tools": tools,
        "response": response,
        "usage": None,
        "totals": totals,
    }

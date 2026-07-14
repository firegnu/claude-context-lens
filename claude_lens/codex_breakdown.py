"""Break a single reconstructed Codex model call into the five contract layers.

The output shape matches what `contract.validate_breakdown` requires (and mirrors
the Claude-side `breakdown.py`), so the macOS app renders Codex calls unchanged.

Codex/OpenAI field mapping (ticket 04):
  L1 request_config <- turn_context (model / effort / sandbox_policy / ...)
  L2 system         <- session_meta.base_instructions + developer-role messages
  L3 messages       <- user messages + tool-call activity (name / arguments / output)
  L4 tools          <- empty, flagged `tools_available: False` (rollouts carry no
                       tool *schemas*; the tool *calls* still surface in L3)
  L5 response       <- this call's agent message(s) + reasoning placeholders
  usage             <- event_msg.token_count.info

reasoning is server-side encrypted (like Claude's redacted thinking): represented
as an unavailable placeholder with zero chars so the encrypted blob never inflates
counts.
"""
import json

# turn_context fields surfaced as L1 config, in display order. turn_context carries
# many more keys; these are the ones that describe how the call was configured.
CODEX_CONFIG_KEYS = ["model", "effort", "sandbox_policy", "approval_policy",
                     "collaboration_mode", "personality", "cwd"]


def _as_text(value):
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def build_codex_breakdown(call):
    """Assemble one model call's five-layer breakdown from a reconstructed `call`.

    `call` is a dict produced by the ingest decomposer with keys:
      turn_context (dict), base_instructions (str), developer_messages (list[str]),
      user_messages (list[str]), tool_calls (list[{name, arguments, output}]),
      agent_messages (list[str]), reasoning_count (int), usage (dict|None).
    """
    turn_context = call.get("turn_context") or {}

    system = []
    base = call.get("base_instructions") or ""
    if base:
        system.append({"index": len(system), "type": "base_instructions",
                       "chars": len(base), "text": base})
    for dev in call.get("developer_messages") or []:
        system.append({"index": len(system), "type": "developer",
                       "chars": len(dev), "text": dev})

    messages = []

    def _add_message(role, mtype, text, extra=None):
        entry = {"message_index": len(messages), "content_index": 0,
                 "role": role, "type": mtype, "chars": len(text), "text": text}
        if extra:
            entry.update(extra)
        messages.append(entry)

    # History was compacted upstream of this call. Flag the boundary honestly (zero
    # chars, available:false) instead of replaying the pre-compaction history or
    # pretending the reconstructed context is complete.
    for _ in range(call.get("compaction_count") or 0):
        _add_message("system", "compaction_boundary", "", {"available": False})
    for user in call.get("user_messages") or []:
        _add_message("user", "message", user)
    for tc in call.get("tool_calls") or []:
        args = _as_text(tc.get("arguments"))
        _add_message("assistant", "tool_call", args,
                     {"tool_name": tc.get("name"), "tool_use_id": tc.get("call_id")})
        if tc.get("output") is not None:
            out = _as_text(tc.get("output"))
            _add_message("tool", "tool_result", out, {"tool_use_id": tc.get("call_id")})

    response = []
    for _ in range(call.get("reasoning_count") or 0):
        # Encrypted server-side; content is unrecoverable, so zero chars + flag.
        response.append({"index": len(response), "type": "reasoning",
                         "available": False, "chars": 0, "text": ""})
    for agent in call.get("agent_messages") or []:
        response.append({"index": len(response), "type": "message",
                         "role": "assistant", "chars": len(agent), "text": agent})
    response = response or None

    totals = {
        "system_chars": sum(s["chars"] for s in system),
        "message_chars": sum(m["chars"] for m in messages),
        # Tool *definitions* aren't in the rollout, so there are no tool chars.
        "tool_description_chars": 0,
        "tool_schema_chars": 0,
    }

    return {
        "request_config": {k: turn_context[k] for k in CODEX_CONFIG_KEYS
                           if k in turn_context},
        "system": system,
        "messages": messages,
        "tools": [],
        # Additive, backward-compatible flag: distinguishes "no tool schemas
        # captured" from "no tools used". Tool calls still appear in L3.
        "tools_available": False,
        "response": response,
        "usage": call.get("usage"),
        "totals": totals,
    }

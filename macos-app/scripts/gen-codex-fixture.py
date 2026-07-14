#!/usr/bin/env python3
"""Regenerate the Codex decode fixtures from the real Python ingest.

The Swift decode tests (SessionDecodeTests / BreakdownDecodeTests) must prove the
app can decode what `codex_ingest` actually produces — not a hand-written guess. So
this feeds a synthetic rollout (public-safe: no real code/PII) through the real
ingest and snapshots the resulting session.json + one breakdown.json as fixtures.

Run after any change to the Codex contract mapping:
    python macos-app/scripts/gen-codex-fixture.py
"""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "macos-app" / "Tests" / "ContextLensCoreTests" / "Fixtures"
sys.path.insert(0, str(REPO))

from claude_lens import codex_ingest  # noqa: E402

# A synthetic rollout exercising every Codex-specific contract feature:
# per-call decomposition (token_count), reasoning placeholder, tool call + output,
# a compaction boundary, and a multi-agent signal.
EVENTS = [
    {"type": "session_meta", "payload": {"base_instructions": "You are Codex.", "session_id": "codex-fixture"}},
    {"type": "turn_context", "payload": {"model": "gpt-5-codex", "effort": "high",
                                         "sandbox_policy": "workspace-write", "approval_policy": "on-request"}},
    {"type": "response_item", "payload": {"type": "message", "role": "developer",
        "content": [{"type": "input_text", "text": "<user_instructions>be terse</user_instructions>"}]}},
    {"type": "event_msg", "payload": {"type": "user_message", "message": "add a test"}},
    {"type": "response_item", "payload": {"type": "reasoning", "encrypted_content": "BLOB" * 20, "summary": []}},
    {"type": "response_item", "payload": {"type": "function_call", "name": "shell",
                                          "arguments": "{\"cmd\":\"ls\"}", "call_id": "c1"}},
    {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1", "output": "file.py"}},
    {"type": "event_msg", "payload": {"type": "agent_message", "message": "ran ls"}},
    {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 1200},
                                                                      "model_context_window": 200000}}},
    {"type": "compacted", "payload": {"message": "summarized", "replacement_history": []}},
    {"type": "event_msg", "payload": {"type": "context_compacted"}},
    {"type": "response_item", "payload": {"type": "reasoning", "encrypted_content": "BLOB" * 10, "summary": []}},
    {"type": "event_msg", "payload": {"type": "agent_message", "message": "done"}},
    {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 1500},
                                                                      "model_context_window": 200000}}},
    {"type": "inter_agent_communication_metadata", "payload": {"from": "a", "to": "b"}},
]


def main():
    with tempfile.TemporaryDirectory() as d:
        rollout = Path(d) / "rollout-fixture.jsonl"
        rollout.write_text("\n".join(json.dumps(e) for e in EVENTS) + "\n", encoding="utf-8")
        out = Path(d) / "out"
        session = codex_ingest.ingest_codex_session(rollout, out, captured_at="2026-01-01T00:00:00Z")
        (FIXTURES / "codex-session.json").write_text((out / "session.json").read_text(), encoding="utf-8")
        first_bd = session["turns"][0]["requests"][0]["breakdown"]
        (FIXTURES / "codex-breakdown.json").write_text((out / first_bd).read_text(), encoding="utf-8")
    print("wrote codex-session.json + codex-breakdown.json to", FIXTURES)


if __name__ == "__main__":
    main()

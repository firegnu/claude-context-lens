import unittest

from claude_lens import breakdown


class BuildBreakdownTest(unittest.TestCase):
    def _request(self):
        return {
            "model": "claude-test",
            "betas": ["b-2025-01-01"],
            "system": [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
            "messages": [
                {"role": "user", "content": "plain string"},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1",
                     "content": "\x1b[1mMakefile\x1b[0m\nREADME", "is_error": False}
                ]},
            ],
            "tools": [{"name": "Read", "description": "read", "input_schema": {"type": "object"}}],
        }

    def test_string_content_becomes_text_block(self):
        bd = breakdown.build_breakdown(self._request(), None)
        first = bd["messages"][0]
        self.assertEqual(first["type"], "text")
        self.assertEqual(first["text"], "plain string")

    def test_tool_result_ansi_stripped_and_metadata_kept(self):
        bd = breakdown.build_breakdown(self._request(), None)
        tr = bd["messages"][1]
        self.assertEqual(tr["tool_use_id"], "toolu_1")
        self.assertIn("Makefile\nREADME", tr["text"])
        self.assertNotIn("\x1b", tr["text"])

    def test_totals_and_usage(self):
        resp = {"content": [{"type": "text", "text": "pong"}], "usage": {"input_tokens": 5}}
        bd = breakdown.build_breakdown(self._request(), resp)
        self.assertEqual(bd["totals"]["system_chars"], 3)
        self.assertGreater(bd["totals"]["tool_schema_chars"], 0)
        self.assertEqual(bd["usage"], {"input_tokens": 5})
        self.assertEqual(bd["response"][0]["text"], "pong")
        self.assertEqual(bd["request_config"]["betas"], ["b-2025-01-01"])

    def test_thinking_block_in_response_is_marked_unavailable(self):
        # Claude Code redacts thinking in telemetry; we must not leak the base64
        # signature into chars, and must flag the content as unavailable.
        resp = {"content": [
            {"type": "thinking", "thinking": "<REDACTED>", "signature": "EpcGCmMIDxgC" * 40},
            {"type": "text", "text": "hi"},
        ]}
        bd = breakdown.build_breakdown(self._request(), resp)
        thinking = bd["response"][0]
        self.assertEqual(thinking["type"], "thinking")
        self.assertFalse(thinking["available"])
        self.assertEqual(thinking["chars"], 0)
        self.assertEqual(thinking["text"], "")
        self.assertEqual(bd["response"][1]["text"], "hi")

    def test_thinking_block_in_message_does_not_inflate_message_chars(self):
        req = self._request()
        req["messages"].append({"role": "assistant", "content": [
            {"type": "thinking", "thinking": "<REDACTED>", "signature": "x" * 500},
        ]})
        bd = breakdown.build_breakdown(req, None)
        msg = bd["messages"][-1]
        self.assertEqual(msg["type"], "thinking")
        self.assertFalse(msg["available"])
        self.assertEqual(msg["chars"], 0)
        self.assertEqual(msg["text"], "")

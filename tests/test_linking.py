import json
import tempfile
import unittest
from pathlib import Path

from claude_lens import linking


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


class LinkRequestsTest(unittest.TestCase):
    def _raw(self, d):
        raw = Path(d) / "raw"
        raw.mkdir()
        # round 0: start (no previous), response id r0
        _write(raw / "a.request.json", {"model": "m", "messages": [{"role": "user", "content": "hi"}]})
        _write(raw / "r0.response.json", {"id": "r0", "stop_reason": "tool_use"})
        # round 1: previous_message_id r0, response id r1
        _write(raw / "b.request.json", {"model": "m", "messages": [1, 2, 3],
                                        "diagnostics": {"previous_message_id": "r0"}})
        _write(raw / "r1.response.json", {"id": "r1", "stop_reason": "end_turn"})
        return raw

    def test_orders_and_pairs(self):
        with tempfile.TemporaryDirectory() as d:
            result = linking.link_requests(self._raw(d))
            ordered = result["ordered"]
            self.assertEqual([o["request_file"] for o in ordered], ["a.request.json", "b.request.json"])
            self.assertEqual(ordered[0]["order_confidence"], "high:start")
            # request 0's own response is inferred from request 1's previous_message_id -> r0
            self.assertEqual(ordered[0]["inferred_response_file"], "r0.response.json")
            # last request falls back to the remaining response r1
            self.assertEqual(ordered[1]["inferred_response_file"], "r1.response.json")

    def test_order_ambiguity_uses_kind(self):
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "raw"
            raw.mkdir()
            # two requests, both without a previous_message_id -> index 1 is medium:null-prev
            _write(raw / "a.request.json", {"messages": [{"role": "user", "content": "hi"}]})
            _write(raw / "b.request.json", {"messages": [{"role": "user", "content": "hi"}, 1]})
            result = linking.link_requests(raw)
            self.assertIn({"kind": "order", "file": "b.request.json", "detail": "medium:null-prev"},
                          result["ambiguities"])

    def test_corrupt_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            raw = self._raw(d)
            (raw / "bad.request.json").write_text("{not json", encoding="utf-8")
            result = linking.link_requests(raw)
            self.assertEqual(len(result["ordered"]), 2)
            self.assertIn({"kind": "corrupt-request", "file": "bad.request.json", "detail": None},
                          result["ambiguities"])

    def test_corrupt_response_file_is_ambiguity_and_excluded_from_responses(self):
        with tempfile.TemporaryDirectory() as d:
            raw = self._raw(d)
            (raw / "bad.response.json").write_text("{not json", encoding="utf-8")
            result = linking.link_requests(raw)
            self.assertIn({"kind": "corrupt-response", "file": "bad.response.json", "detail": None},
                          result["ambiguities"])
            self.assertNotIn("bad.response.json", [r["file"] for r in result["responses"]])
            self.assertEqual(len(result["responses"]), 2)

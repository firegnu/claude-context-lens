import tempfile
import unittest
from pathlib import Path

from claude_lens import contract


class ContractTest(unittest.TestCase):
    def test_read_write_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "x.json"
            contract.write_json(p, {"a": 1, "z": "你好"})
            self.assertEqual(contract.read_json(p), {"a": 1, "z": "你好"})

    def test_validate_session_flags_missing_keys(self):
        problems = contract.validate_session({"turns": []})
        self.assertTrue(any("session_id" in p for p in problems))

    def _minimal_request(self):
        return {"index": 0, "raw_request": "raw/a", "raw_response": None, "breakdown": "derived/b",
                "order_confidence": "high:start", "is_sidechannel": False, "usage": None, "totals": {}}

    def _minimal_session(self):
        return {
            "session_id": "s", "captured_at": "t", "launcher_argv": ["claude"], "model": "m",
            "counts": {}, "ambiguities": [], "sidechannel": [],
            "turns": [{"index": 0, "user_message_preview": "p", "requests": [self._minimal_request()]}],
        }

    def test_validate_session_accepts_minimal_valid(self):
        self.assertEqual(contract.validate_session(self._minimal_session()), [])

    def test_validate_session_flags_request_missing_new_required_keys(self):
        session = self._minimal_session()
        del session["turns"][0]["requests"][0]["usage"]
        self.assertTrue(any("usage" in p for p in contract.validate_session(session)))

    def test_validate_session_flags_turn_missing_preview(self):
        session = self._minimal_session()
        del session["turns"][0]["user_message_preview"]
        self.assertTrue(any("user_message_preview" in p for p in contract.validate_session(session)))

    def test_validate_session_checks_sidechannel_requests(self):
        session = self._minimal_session()
        session["sidechannel"] = [{"index": 0, "raw_request": "raw/x"}]  # missing most keys
        self.assertTrue(any("sidechannel" in p for p in contract.validate_session(session)))

    def test_validate_breakdown_flags_missing_keys(self):
        self.assertTrue(any("usage" in p for p in contract.validate_breakdown({"system": []})))

    def test_validate_breakdown_accepts_valid_with_null_response(self):
        bd = {"request_config": {}, "system": [], "messages": [], "tools": [],
              "response": None, "usage": None, "totals": {}}
        self.assertEqual(contract.validate_breakdown(bd), [])

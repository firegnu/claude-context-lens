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

    def test_validate_session_accepts_minimal_valid(self):
        session = {
            "session_id": "s", "captured_at": "t", "model": "m",
            "counts": {}, "ambiguities": [],
            "turns": [{"index": 0, "requests": [
                {"index": 0, "raw_request": "raw/a", "breakdown": "derived/b", "order_confidence": "high:start"}
            ]}],
        }
        self.assertEqual(contract.validate_session(session), [])

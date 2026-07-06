import json
import tempfile
import unittest
from pathlib import Path

from claude_lens import contract, ingest


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class IngestSessionTest(unittest.TestCase):
    def _session_dir(self, d):
        sd = Path(d) / "20260101-000000"
        raw = sd / "raw"
        _write(raw / "a.request.json", {"model": "claude-x", "system": [{"type": "text", "text": "S"}],
                                        "messages": [{"role": "user", "content": "hi"}], "tools": []})
        _write(raw / "r0.response.json", {"id": "r0", "content": [{"type": "text", "text": "pong"}],
                                          "usage": {"input_tokens": 7}, "stop_reason": "end_turn"})
        return sd

    def test_writes_valid_session_and_breakdown(self):
        with tempfile.TemporaryDirectory() as d:
            sd = self._session_dir(d)
            session = ingest.ingest_session(sd, captured_at="2026-01-01T00:00:00Z", launcher_argv=["claude"])
            self.assertEqual(contract.validate_session(session), [])
            self.assertEqual(session["counts"]["turns"], 1)
            self.assertEqual(session["counts"]["requests"], 1)
            self.assertEqual(session["model"], "claude-x")
            req = session["turns"][0]["requests"][0]
            self.assertEqual(req["raw_response"], "raw/r0.response.json")
            self.assertEqual(req["usage"], {"input_tokens": 7})
            self.assertTrue((sd / "derived" / "req-000.breakdown.json").exists())
            self.assertTrue((sd / "session.json").exists())

    def test_sidechannel_request_separated_and_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d) / "sc"
            raw = sd / "raw"
            _write(raw / "a.request.json", {"model": "claude-x", "system": [],
                                            "messages": [{"role": "user", "content": "real"}], "tools": []})
            _write(raw / "s.request.json", {"model": "claude-x", "system": [],
                                            "messages": [{"role": "user", "content": "[SUGGESTION MODE: next]"}],
                                            "tools": []})
            session = ingest.ingest_session(sd, captured_at="t", launcher_argv=["claude"])
            self.assertEqual(contract.validate_session(session), [])
            self.assertEqual(session["counts"]["sidechannel"], 1)
            self.assertEqual(len(session["sidechannel"]), 1)
            self.assertTrue(session["sidechannel"][0]["is_sidechannel"])
            self.assertEqual(session["sidechannel"][0]["raw_request"], "raw/s.request.json")
            turn_reqs = [r for t in session["turns"] for r in t["requests"]]
            self.assertEqual([r["raw_request"] for r in turn_reqs], ["raw/a.request.json"])
            self.assertTrue(all(not r["is_sidechannel"] for r in turn_reqs))

    def test_empty_session_is_valid(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d) / "empty"
            (sd / "raw").mkdir(parents=True)
            session = ingest.ingest_session(sd, captured_at="t", launcher_argv=None)
            self.assertEqual(session["counts"]["requests"], 0)
            self.assertEqual(session["turns"], [])
            self.assertIsNone(session["model"])
            self.assertEqual(contract.validate_session(session), [])

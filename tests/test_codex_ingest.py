import json
import tempfile
import unittest
from pathlib import Path

from claude_lens import contract, codex_ingest


def _write_rollout(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


class IngestCodexSessionTest(unittest.TestCase):
    def _minimal_rollout(self, d):
        rollout = Path(d) / "rollout-min.jsonl"
        _write_rollout(rollout, [
            {"type": "session_meta", "timestamp": "t0",
             "payload": {"base_instructions": "You are Codex.",
                         "session_id": "sess-1", "model_provider": "openai"}},
            {"type": "event_msg", "timestamp": "t1",
             "payload": {"type": "user_message", "message": "hello codex"}},
            {"type": "event_msg", "timestamp": "t2",
             "payload": {"type": "agent_message", "message": "hi there"}},
        ])
        return rollout

    def test_minimal_rollout_produces_valid_session(self):
        with tempfile.TemporaryDirectory() as d:
            rollout = self._minimal_rollout(d)
            session_dir = Path(d) / "out"
            session = codex_ingest.ingest_codex_session(
                rollout, session_dir, captured_at="2026-01-01T00:00:00Z")

            self.assertEqual(contract.validate_session(session), [])
            self.assertEqual(session["counts"]["turns"], 1)
            self.assertEqual(session["counts"]["requests"], 1)
            self.assertTrue((session_dir / "session.json").exists())

            req = session["turns"][0]["requests"][0]
            bd = contract.read_json(session_dir / req["breakdown"])
            self.assertEqual(contract.validate_breakdown(bd), [])

            # L2 system carries base_instructions
            self.assertTrue(any("You are Codex." in s.get("text", "") for s in bd["system"]))
            # L3 messages carries the user turn (what was sent)
            self.assertIn("hello codex", " ".join(m.get("text", "") for m in bd["messages"]))
            # L5 response carries the agent reply
            self.assertIn("hi there", " ".join(r.get("text", "") for r in (bd["response"] or [])))

    def test_empty_rollout_is_valid(self):
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "empty.jsonl"
            rollout.write_text("", encoding="utf-8")
            session_dir = Path(d) / "out"
            session = codex_ingest.ingest_codex_session(
                rollout, session_dir, captured_at="t")
            self.assertEqual(contract.validate_session(session), [])
            self.assertEqual(session["counts"]["requests"], 0)
            self.assertEqual(session["turns"], [])


if __name__ == "__main__":
    unittest.main()

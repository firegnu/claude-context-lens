import json
import tempfile
import unittest
from pathlib import Path

from claude_lens import contract, codex_ingest


def _write_rollout(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def _write_rollout_lines(path, lines):
    """Write raw JSONL lines verbatim, so a fixture can include malformed input."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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

    def test_ingest_skips_unknown_and_malformed_without_crashing(self):
        # Mirrors what real rollouts carry (verified 2026-07-14): event kinds the
        # skeleton does not consume yet (reasoning, token_count, world_state,
        # inter_agent_communication_metadata, compacted) plus malformed lines. Ingest
        # must skip them without crashing, still validate, and *count* every skip.
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "rollout-mixed.jsonl"
            _write_rollout_lines(rollout, [
                json.dumps({"type": "session_meta", "payload": {
                    "base_instructions": "You are Codex.", "session_id": "sess-x"}}),
                json.dumps({"type": "turn_context", "payload": {"model": "gpt-x"}}),
                json.dumps({"type": "event_msg",
                            "payload": {"type": "user_message", "message": "hi"}}),
                json.dumps({"type": "response_item",
                            "payload": {"type": "reasoning", "encrypted_content": "xx"}}),
                json.dumps({"type": "event_msg",
                            "payload": {"type": "agent_message", "message": "hello"}}),
                json.dumps({"type": "event_msg",
                            "payload": {"type": "token_count", "info": {}}}),
                json.dumps({"type": "world_state", "payload": {"full": {}}}),
                json.dumps({"type": "inter_agent_communication_metadata", "payload": {}}),
                json.dumps({"type": "compacted", "payload": {"replacement_history": []}}),
                "this is not valid json {",       # malformed line -> skipped + counted
                "42",                              # valid json but not an object -> skipped + counted
            ])
            session_dir = Path(d) / "out"
            session = codex_ingest.ingest_codex_session(
                rollout, session_dir, captured_at="t")

            # Still a valid, renderable session despite the unknown/broken input.
            self.assertEqual(contract.validate_session(session), [])
            self.assertEqual(session["counts"]["turns"], 1)
            self.assertEqual(session["counts"]["requests"], 1)

            # Skips are counted, not silently swallowed.
            ingest = session["ingest"]
            self.assertEqual(ingest["malformed_lines"], 2)
            self.assertEqual(ingest["events_total"], 9)  # 9 well-formed object events
            skipped = ingest["skipped_kinds"]
            self.assertEqual(skipped["response_item.reasoning"], 1)
            self.assertEqual(skipped["event_msg.token_count"], 1)
            self.assertEqual(skipped["world_state"], 1)
            self.assertEqual(skipped["inter_agent_communication_metadata"], 1)
            self.assertEqual(skipped["compacted"], 1)
            # Consumed kinds are not reported as skipped.
            for consumed in ("session_meta", "turn_context",
                             "event_msg.user_message", "event_msg.agent_message"):
                self.assertNotIn(consumed, skipped)

            # events_by_kind is the complete census — every well-formed event lands
            # in it (consumed kinds included), so nothing is silently swallowed even
            # where skipped_kinds excludes a kind the reconstruction only partly uses.
            by_kind = ingest["events_by_kind"]
            self.assertEqual(sum(by_kind.values()), ingest["events_total"])
            self.assertEqual(by_kind["event_msg.user_message"], 1)
            self.assertEqual(by_kind["event_msg.agent_message"], 1)
            self.assertEqual(by_kind["world_state"], 1)

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

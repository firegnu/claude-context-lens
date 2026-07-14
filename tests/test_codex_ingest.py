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

    def test_multi_turn_segmentation_groups_requests_by_user_message(self):
        # A multi-turn stream: each event_msg.user_message opens a turn; the
        # agent_messages that follow, until the next user_message, are that turn's
        # response. Requests must land in the right turn, previews on the right turn.
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "rollout-multi.jsonl"
            _write_rollout(rollout, [
                {"type": "session_meta",
                 "payload": {"base_instructions": "You are Codex.", "session_id": "s2"}},
                {"type": "turn_context", "payload": {"model": "gpt-x"}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "first task"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "working"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "done first"}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "second task"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "done second"}},
            ])
            session_dir = Path(d) / "out"
            session = codex_ingest.ingest_codex_session(
                rollout, session_dir, captured_at="t")

            self.assertEqual(contract.validate_session(session), [])
            self.assertEqual(session["counts"]["turns"], 2)
            self.assertEqual(session["counts"]["requests"], 2)

            turn0, turn1 = session["turns"]
            self.assertTrue(turn0["user_message_preview"].startswith("first task"))
            self.assertTrue(turn1["user_message_preview"].startswith("second task"))
            self.assertEqual(len(turn0["requests"]), 1)
            self.assertEqual(len(turn1["requests"]), 1)

            # Each turn's response holds only that turn's agent messages (grouping).
            bd0 = contract.read_json(session_dir / turn0["requests"][0]["breakdown"])
            bd1 = contract.read_json(session_dir / turn1["requests"][0]["breakdown"])
            r0 = " ".join(r.get("text", "") for r in (bd0["response"] or []))
            r1 = " ".join(r.get("text", "") for r in (bd1["response"] or []))
            self.assertIn("working", r0)
            self.assertIn("done first", r0)
            self.assertNotIn("done second", r0)
            self.assertIn("done second", r1)
            self.assertNotIn("working", r1)

    def test_user_turns_come_from_event_msg_not_injected_response_items(self):
        # AC #3 lock: user turns are segmented on event_msg.user_message ONLY.
        # Real rollouts also carry role=user response_item.message entries that are
        # Codex-injected context (<environment_context>, <user_instructions>, ...),
        # which outnumber the human turns. Those must NOT create extra turns.
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "rollout-injected.jsonl"
            _write_rollout(rollout, [
                {"type": "session_meta",
                 "payload": {"base_instructions": "You are Codex.", "session_id": "s3"}},
                # injected user-role context item in the preamble -> not a turn
                {"type": "response_item", "payload": {
                    "type": "message", "role": "user",
                    "content": [{"type": "input_text", "text": "<environment_context>cwd</environment_context>"}]}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "real one"}},
                # injected user-role item mid-turn -> not a turn
                {"type": "response_item", "payload": {
                    "type": "message", "role": "user",
                    "content": [{"type": "input_text", "text": "<user_instructions>be terse</user_instructions>"}]}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "ok"}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "real two"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "ok2"}},
            ])
            session_dir = Path(d) / "out"
            session = codex_ingest.ingest_codex_session(
                rollout, session_dir, captured_at="t")

            self.assertEqual(contract.validate_session(session), [])
            # Two human turns, despite two extra role=user response_item.message items.
            self.assertEqual(session["counts"]["turns"], 2)
            previews = [t["user_message_preview"] for t in session["turns"]]
            self.assertTrue(previews[0].startswith("real one"))
            self.assertTrue(previews[1].startswith("real two"))
            # Injected wrapper text never becomes a turn preview.
            self.assertFalse(any("environment_context" in p for p in previews))
            self.assertFalse(any("user_instructions" in p for p in previews))


if __name__ == "__main__":
    unittest.main()

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
            # world_state is still consumed by nothing, so it stays flagged.
            self.assertEqual(skipped["world_state"], 1)
            # Consumed kinds are not reported as skipped — usage + reasoning (t04),
            # compacted (t05, flagged boundary), inter_agent (t06, detection signal).
            for consumed in ("session_meta", "turn_context",
                             "event_msg.user_message", "event_msg.agent_message",
                             "event_msg.token_count", "response_item.reasoning",
                             "compacted", "inter_agent_communication_metadata"):
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


class PerCallBreakdownTest(unittest.TestCase):
    """Ticket 04: per-model-call decomposition (token_count-delimited) and the
    five-layer breakdown filled from real Codex event kinds."""

    def _dev_msg(self, text):
        return {"type": "response_item", "payload": {
            "type": "message", "role": "developer",
            "content": [{"type": "input_text", "text": text}]}}

    def _real_rollout(self, path):
        _write_rollout(path, [
            {"type": "session_meta", "payload": {
                "base_instructions": "You are Codex.", "session_id": "s4"}},
            self._dev_msg("<user_instructions>be terse</user_instructions>"),
            {"type": "turn_context", "payload": {
                "model": "gpt-5-codex", "effort": "high",
                "sandbox_policy": "workspace-write", "approval_policy": "on-request"}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "add a test"}},
            # --- model call 1: reasoning + a tool call + its result + an agent message ---
            {"type": "response_item", "payload": {
                "type": "reasoning", "encrypted_content": "BLOB" * 50, "summary": []}},
            {"type": "response_item", "payload": {
                "type": "function_call", "name": "shell",
                "arguments": "{\"cmd\":\"ls\"}", "call_id": "c1"}},
            {"type": "response_item", "payload": {
                "type": "function_call_output", "call_id": "c1", "output": "file.py listed"}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "I ran ls"}},
            {"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {}, "info": {
                "total_token_usage": {"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200},
                "last_token_usage": {"input_tokens": 500, "output_tokens": 100},
                "model_context_window": 200000}}},
            # --- model call 2: reasoning + final agent message ---
            {"type": "response_item", "payload": {
                "type": "reasoning", "encrypted_content": "BLOB" * 30, "summary": []}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "Done, added the test"}},
            {"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {}, "info": {
                "total_token_usage": {"input_tokens": 1300, "output_tokens": 260, "total_tokens": 1560},
                "last_token_usage": {"input_tokens": 300, "output_tokens": 60},
                "model_context_window": 200000}}},
        ])

    def test_turn_decomposes_into_token_count_delimited_calls(self):
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "rollout-real.jsonl"
            self._real_rollout(rollout)
            session_dir = Path(d) / "out"
            session = codex_ingest.ingest_codex_session(
                rollout, session_dir, captured_at="t")

            self.assertEqual(contract.validate_session(session), [])
            self.assertEqual(session["counts"]["turns"], 1)
            # Two token_count events -> two model calls in the one turn.
            self.assertEqual(session["counts"]["requests"], 2)
            self.assertEqual(len(session["turns"][0]["requests"]), 2)

    def _breakdowns(self, d):
        rollout = Path(d) / "rollout-real.jsonl"
        self._real_rollout(rollout)
        session_dir = Path(d) / "out"
        session = codex_ingest.ingest_codex_session(rollout, session_dir, captured_at="t")
        reqs = session["turns"][0]["requests"]
        bds = [contract.read_json(session_dir / r["breakdown"]) for r in reqs]
        for bd in bds:
            self.assertEqual(contract.validate_breakdown(bd), [])
        return session, bds

    def test_l1_config_from_turn_context(self):
        with tempfile.TemporaryDirectory() as d:
            _, bds = self._breakdowns(d)
            cfg = bds[0]["request_config"]
            self.assertEqual(cfg["model"], "gpt-5-codex")
            self.assertEqual(cfg["effort"], "high")
            self.assertEqual(cfg["sandbox_policy"], "workspace-write")
            self.assertEqual(cfg["approval_policy"], "on-request")

    def test_l2_system_has_base_and_developer(self):
        with tempfile.TemporaryDirectory() as d:
            _, bds = self._breakdowns(d)
            sys_text = " ".join(s["text"] for s in bds[0]["system"])
            self.assertIn("You are Codex.", sys_text)
            self.assertIn("be terse", sys_text)
            types = {s["type"] for s in bds[0]["system"]}
            self.assertIn("base_instructions", types)
            self.assertIn("developer", types)

    def test_l3_has_user_message_and_tool_call_activity(self):
        with tempfile.TemporaryDirectory() as d:
            _, bds = self._breakdowns(d)
            msgs = bds[0]["messages"]
            joined = " ".join(m["text"] for m in msgs)
            # user message (first call of the turn)
            self.assertIn("add a test", joined)
            # tool call name + arguments, and the tool result, live in L3
            self.assertTrue(any(m.get("tool_name") == "shell" for m in msgs))
            self.assertIn("ls", joined)            # arguments
            self.assertIn("file.py listed", joined)  # tool result output

    def test_l4_tools_empty_and_flagged_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            _, bds = self._breakdowns(d)
            self.assertEqual(bds[0]["tools"], [])
            # tool *schemas* are absent from rollouts -> flagged, not silently "no tools"
            self.assertFalse(bds[0]["tools_available"])

    def test_l5_reasoning_is_unavailable_placeholder_with_zero_chars(self):
        with tempfile.TemporaryDirectory() as d:
            _, bds = self._breakdowns(d)
            resp = bds[0]["response"]
            reasoning = [r for r in resp if r["type"] == "reasoning"]
            self.assertTrue(reasoning)
            for r in reasoning:
                self.assertFalse(r["available"])
                self.assertEqual(r["chars"], 0)
                self.assertEqual(r["text"], "")
            # the agent message is present as readable response text
            self.assertIn("I ran ls", " ".join(r["text"] for r in resp))

    def test_encrypted_reasoning_never_inflates_totals(self):
        with tempfile.TemporaryDirectory() as d:
            _, bds = self._breakdowns(d)
            # the 200-char "BLOB..." encrypted_content must not appear anywhere countable
            for bd in bds:
                blob_in_texts = any("BLOB" in s["text"] for s in bd["system"]) \
                    or any("BLOB" in m["text"] for m in bd["messages"]) \
                    or any("BLOB" in r["text"] for r in (bd["response"] or []))
                self.assertFalse(blob_in_texts)

    def test_usage_from_token_count(self):
        with tempfile.TemporaryDirectory() as d:
            session, bds = self._breakdowns(d)
            usage0 = bds[0]["usage"]
            self.assertEqual(usage0["total_token_usage"]["total_tokens"], 1200)
            self.assertEqual(usage0["model_context_window"], 200000)
            # second call carries its own usage record
            self.assertEqual(bds[1]["usage"]["total_token_usage"]["total_tokens"], 1560)
            # request meta mirrors the breakdown usage
            self.assertEqual(session["turns"][0]["requests"][0]["usage"], usage0)

    def test_totals_count_system_message_and_tool_chars(self):
        with tempfile.TemporaryDirectory() as d:
            _, bds = self._breakdowns(d)
            totals = bds[0]["totals"]
            self.assertEqual(totals["system_chars"],
                             sum(s["chars"] for s in bds[0]["system"]))
            self.assertEqual(totals["message_chars"],
                             sum(m["chars"] for m in bds[0]["messages"]))
            self.assertGreater(totals["system_chars"], 0)
            self.assertGreater(totals["message_chars"], 0)

    def test_reconstruction_fidelity_gap_is_disclosed(self):
        # US18: the per-call-local L3 (not a full-context replay) must be surfaced
        # in the contract, not just in code comments.
        with tempfile.TemporaryDirectory() as d:
            session, _ = self._breakdowns(d)
            notes = [a for a in session["ambiguities"] if a["kind"] == "reconstruction"]
            self.assertEqual(len(notes), 1)
            self.assertIn("not a verbatim", notes[0]["detail"])

    def test_raw_request_is_empty_string_not_null(self):
        # The macOS app's Codable decoder types raw_request as a NON-optional String;
        # Codex has no verbatim wire body, but must emit "" (not null) or the app
        # can't decode the session. This pins the cross-language contract value that
        # the Swift decode test (macos-app) also guards, so reverting to None here
        # fails fast in Python instead of only surfacing on fixture regeneration.
        with tempfile.TemporaryDirectory() as d:
            session, _ = self._breakdowns(d)
            for turn in session["turns"]:
                for req in turn["requests"]:
                    self.assertEqual(req["raw_request"], "")

    def test_dict_base_instructions_extracted_and_all_text_is_string(self):
        # Real Codex wraps base_instructions as {"text": ...}. The app's decoder
        # types every layer's text as a String, so ingest must extract the text
        # (not pass the dict through), and no layer's text may be a non-string.
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "rollout-dict-base.jsonl"
            _write_rollout(rollout, [
                {"type": "session_meta", "payload": {
                    "base_instructions": {"text": "wrapped base"}, "session_id": "sb"}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "hi"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "ok"}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {}}},
            ])
            session = codex_ingest.ingest_codex_session(rollout, Path(d) / "out", captured_at="t")
            bd = contract.read_json(Path(d) / "out" / session["turns"][0]["requests"][0]["breakdown"])
            base = next(s for s in bd["system"] if s["type"] == "base_instructions")
            self.assertEqual(base["text"], "wrapped base")   # extracted, not the {"text":...} dict
            for layer in ("system", "messages"):
                for entry in bd[layer]:
                    self.assertIsInstance(entry["text"], str)
            for entry in (bd["response"] or []):
                self.assertIsInstance(entry["text"], str)

    def test_object_wrapped_user_message_does_not_crash_ingest(self):
        # Defense-in-depth, symmetric with base_instructions: user/agent messages are
        # strings in every observed rollout, but an object-wrapped one must be coerced,
        # not crash ingest on turn["user"][:120].
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "rollout-wrapped.jsonl"
            _write_rollout(rollout, [
                {"type": "session_meta", "payload": {"session_id": "w"}},
                {"type": "event_msg", "payload": {"type": "user_message",
                                                  "message": {"text": "hi wrapped"}}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "ok"}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {}}},
            ])
            session = codex_ingest.ingest_codex_session(rollout, Path(d) / "out", captured_at="t")
            self.assertEqual(contract.validate_session(session), [])
            self.assertTrue(session["turns"][0]["user_message_preview"].startswith("hi wrapped"))


class CompactionTest(unittest.TestCase):
    """Ticket 05: detect compaction, flag the boundary honestly, never replay
    replacement_history (no full pre-compaction reconstruction in v1)."""

    def _rollout_with_compaction(self, path):
        _write_rollout(path, [
            {"type": "session_meta", "payload": {
                "base_instructions": "You are Codex.", "session_id": "s5"}},
            {"type": "turn_context", "payload": {"model": "gpt-x"}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "long task"}},
            # --- call 1: no compaction ---
            {"type": "response_item", "payload": {"type": "reasoning",
                                                  "encrypted_content": "x", "summary": []}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "step 1"}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"a": 1}}},
            # --- compaction happens here; replacement_history must NEVER be replayed ---
            {"type": "compacted", "payload": {"message": "history summarized",
                "replacement_history": [{"type": "message", "role": "user",
                    "content": [{"type": "input_text", "text": "PRECOMPACTION_SECRET"}]}]}},
            {"type": "event_msg", "payload": {"type": "context_compacted"}},
            # --- call 2: sees the compaction boundary upstream ---
            {"type": "response_item", "payload": {"type": "reasoning",
                                                  "encrypted_content": "x", "summary": []}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "step 2"}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"a": 2}}},
        ])

    def _run(self, d):
        rollout = Path(d) / "rollout-compact.jsonl"
        self._rollout_with_compaction(rollout)
        session_dir = Path(d) / "out"
        session = codex_ingest.ingest_codex_session(rollout, session_dir, captured_at="t")
        reqs = session["turns"][0]["requests"]
        bds = [contract.read_json(session_dir / r["breakdown"]) for r in reqs]
        return session, bds

    def test_compaction_rollout_is_valid_with_two_calls(self):
        with tempfile.TemporaryDirectory() as d:
            session, bds = self._run(d)
            self.assertEqual(contract.validate_session(session), [])
            self.assertEqual(session["counts"]["requests"], 2)
            for bd in bds:
                self.assertEqual(contract.validate_breakdown(bd), [])

    def test_compaction_boundary_flagged_on_the_call_after_it(self):
        with tempfile.TemporaryDirectory() as d:
            _, bds = self._run(d)
            # call 1 (before compaction) has no boundary marker
            self.assertFalse(any(m["type"] == "compaction_boundary" for m in bds[0]["messages"]))
            # call 2 (after compaction) carries an explicit boundary marker
            markers = [m for m in bds[1]["messages"] if m["type"] == "compaction_boundary"]
            self.assertEqual(len(markers), 1)
            self.assertFalse(markers[0]["available"])
            self.assertEqual(markers[0]["chars"], 0)

    def test_replacement_history_is_never_replayed(self):
        with tempfile.TemporaryDirectory() as d:
            _, bds = self._run(d)
            # the pre-compaction history text must appear nowhere in the reconstruction
            for bd in bds:
                for layer in ("system", "messages"):
                    self.assertFalse(any("PRECOMPACTION_SECRET" in e["text"] for e in bd[layer]))
                self.assertFalse(any("PRECOMPACTION_SECRET" in e["text"]
                                     for e in (bd["response"] or [])))

    def test_compaction_disclosed_in_session_and_counted_as_consumed(self):
        with tempfile.TemporaryDirectory() as d:
            session, _ = self._run(d)
            comp = [a for a in session["ambiguities"] if a["kind"] == "compaction"]
            self.assertEqual(len(comp), 1)
            # both paired events are consumed, not misreported as skipped
            skipped = session["ingest"]["skipped_kinds"]
            self.assertNotIn("compacted", skipped)
            self.assertNotIn("event_msg.context_compacted", skipped)

    def test_trailing_lone_compaction_is_disclosed_not_dropped(self):
        # A compacted event with no following model call must not vanish silently
        # (ticket 05's core "never silently drop" invariant) nor become a spurious
        # request. The session disclosure counts it from the event stream directly.
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "rollout-trailing.jsonl"
            _write_rollout(rollout, [
                {"type": "session_meta", "payload": {"session_id": "s6"}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "hi"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "ok"}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {}}},
                # trailing compaction, nothing after it
                {"type": "compacted", "payload": {"message": "x", "replacement_history": []}},
            ])
            session_dir = Path(d) / "out"
            session = codex_ingest.ingest_codex_session(rollout, session_dir, captured_at="t")
            self.assertEqual(contract.validate_session(session), [])
            # one real model call, not a phantom request for the lone compaction
            self.assertEqual(session["counts"]["requests"], 1)
            # but the compaction is still disclosed at session scope
            comp = [a for a in session["ambiguities"] if a["kind"] == "compaction"]
            self.assertEqual(len(comp), 1)
            self.assertIn("1 time", comp[0]["detail"])


class MultiAgentTest(unittest.TestCase):
    """Ticket 06: multi-agent sessions are detected and flagged (not reconstructed).
    Detection is on the inter_agent_communication_metadata EVENT — the
    multi_agent_mode / collaboration_mode / multi_agent_version turn_context fields
    are config defaults present in single-agent sessions too, so they would misflag
    everything (verified across 200 real rollouts)."""

    def test_multi_agent_flagged_on_inter_agent_event(self):
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "rollout-ma.jsonl"
            _write_rollout(rollout, [
                {"type": "session_meta", "payload": {"session_id": "ma1"}},
                {"type": "turn_context", "payload": {"model": "gpt-x"}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "coordinate"}},
                {"type": "inter_agent_communication_metadata",
                 "payload": {"from": "agent-a", "to": "agent-b"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "ok"}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {}}},
            ])
            session = codex_ingest.ingest_codex_session(
                rollout, Path(d) / "out", captured_at="t")
            self.assertEqual(contract.validate_session(session), [])
            self.assertTrue(session["multi_agent"])
            notes = [a for a in session["ambiguities"] if a["kind"] == "multi_agent"]
            self.assertEqual(len(notes), 1)
            # detection is not skipped-swallowed
            self.assertNotIn("inter_agent_communication_metadata",
                             session["ingest"]["skipped_kinds"])

    def test_single_agent_not_flagged_despite_multi_agent_config_fields(self):
        # turn_context carries multi_agent_mode / collaboration_mode / version in
        # single-agent sessions too (config defaults). Without an inter-agent event,
        # this must NOT be flagged, and the reconstruction is unchanged.
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "rollout-sa.jsonl"
            _write_rollout(rollout, [
                {"type": "session_meta", "payload": {
                    "base_instructions": "You are Codex.", "session_id": "sa1"}},
                {"type": "turn_context", "payload": {
                    "model": "gpt-x", "multi_agent_mode": "explicitRequestOnly",
                    "multi_agent_version": "v2",
                    "collaboration_mode": {"mode": "default"}}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "hi"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "hello"}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {}}},
            ])
            session = codex_ingest.ingest_codex_session(
                rollout, Path(d) / "out", captured_at="t")
            self.assertEqual(contract.validate_session(session), [])
            self.assertFalse(session["multi_agent"])
            self.assertFalse(any(a["kind"] == "multi_agent" for a in session["ambiguities"]))
            # reconstruction unaffected
            self.assertEqual(session["counts"]["turns"], 1)
            self.assertEqual(session["counts"]["requests"], 1)


if __name__ == "__main__":
    unittest.main()

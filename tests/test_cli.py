import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from claude_lens import cli, codex_ingest, contract


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_rollout(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def _minimal_rollout_events():
    return [
        {"type": "session_meta", "payload": {"base_instructions": "You are Codex.",
                                             "session_id": "sess-cli"}},
        {"type": "turn_context", "payload": {"model": "gpt-x", "effort": "high"}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "hi"}},
        {"type": "response_item", "payload": {"type": "reasoning",
                                              "encrypted_content": "x", "summary": []}},
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "hello"}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_tokens": 5}}},
    ]


class CliIngestTest(unittest.TestCase):
    def test_ingest_copies_raw_and_writes_session(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "bodies"
            src.mkdir()
            _write(src / "a.request.json", {"model": "m", "messages": [{"role": "user", "content": "hi"}]})
            _write(src / "r0.response.json", {"id": "r0", "content": [], "usage": {}})
            out_root = Path(d) / "store"

            cli.main(["ingest", str(src), "--session-id", "sess1", "--root", str(out_root)])

            session = json.loads((out_root / "sess1" / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(session["session_id"], "sess1")
            self.assertTrue((out_root / "sess1" / "raw" / "a.request.json").exists())


class CliIngestCodexTest(unittest.TestCase):
    def test_ingest_codex_writes_valid_session_with_five_layers(self):
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "rollout-cli.jsonl"
            _write_rollout(rollout, _minimal_rollout_events())
            out_root = Path(d) / "store"

            cli.main(["ingest-codex", str(rollout), "--session-id", "cx1",
                      "--root", str(out_root)])

            session = json.loads((out_root / "cx1" / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(contract.validate_session(session), [])
            self.assertEqual(session["counts"]["requests"], 1)
            req = session["turns"][0]["requests"][0]
            bd = json.loads((out_root / "cx1" / req["breakdown"]).read_text(encoding="utf-8"))
            self.assertEqual(contract.validate_breakdown(bd), [])
            # five layers populated from the rollout
            self.assertTrue(any("You are Codex." in s["text"] for s in bd["system"]))
            self.assertEqual(bd["request_config"]["model"], "gpt-x")
            self.assertIn("hi", " ".join(m["text"] for m in bd["messages"]))
            self.assertTrue(any(r["type"] == "reasoning" for r in bd["response"]))
            self.assertIsNotNone(bd["usage"])

    def test_ingest_codex_defaults_session_id_to_rollout_stem(self):
        with tempfile.TemporaryDirectory() as d:
            rollout = Path(d) / "rollout-abc.jsonl"
            _write_rollout(rollout, _minimal_rollout_events())
            out_root = Path(d) / "store"
            cli.main(["ingest-codex", str(rollout), "--root", str(out_root)])
            self.assertTrue((out_root / "rollout-abc" / "session.json").exists())


class CodexDiscoveryTest(unittest.TestCase):
    def _codex_tree(self, d):
        codex = Path(d) / ".codex"
        _write_rollout(codex / "sessions" / "2026" / "06" / "13" / "rollout-a.jsonl",
                       _minimal_rollout_events())
        _write_rollout(codex / "sessions" / "2025" / "09" / "02" / "rollout-b.jsonl",
                       _minimal_rollout_events())
        return codex

    def test_discover_walks_date_nested_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            codex = self._codex_tree(d)
            found = codex_ingest.discover_codex_rollouts(codex)
            names = [p.name for p in found]
            self.assertEqual(names, ["rollout-b.jsonl", "rollout-a.jsonl"])  # sorted by date path

    def test_discover_empty_when_no_sessions(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(codex_ingest.discover_codex_rollouts(Path(d) / ".codex"), [])

    def test_read_session_index_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            codex = self._codex_tree(d)
            (codex / "session_index.jsonl").write_text(
                json.dumps({"id": "u1", "thread_name": "proj", "updated_at": "t"}) + "\n",
                encoding="utf-8")
            entries = codex_ingest.read_codex_session_index(codex)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["thread_name"], "proj")

    def test_read_session_index_absent_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(codex_ingest.read_codex_session_index(Path(d) / ".codex"), [])

    def test_list_codex_prints_discovered_count(self):
        with tempfile.TemporaryDirectory() as d:
            codex = self._codex_tree(d)
            buf = io.StringIO()
            with redirect_stdout(buf):
                cli.main(["list-codex", "--codex-dir", str(codex)])
            out = buf.getvalue()
            self.assertIn("2 Codex rollout(s)", out)
            self.assertIn("rollout-a.jsonl", out)

    def test_list_codex_prints_session_index_and_tolerates_bad_line(self):
        with tempfile.TemporaryDirectory() as d:
            codex = self._codex_tree(d)
            (codex / "session_index.jsonl").write_text(
                json.dumps({"id": "u1", "thread_name": "proj", "updated_at": "t"}) + "\n"
                + '"not-a-dict"\n',  # hostile non-object line must not crash list-codex
                encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                cli.main(["list-codex", "--codex-dir", str(codex)])
            out = buf.getvalue()
            self.assertIn("session_index.jsonl (1 sessions)", out)
            self.assertIn("proj", out)


class CliRunArgsTest(unittest.TestCase):
    def test_run_passes_dash_prefixed_args_through(self):
        with patch("claude_lens.cli.run_session") as mock_run_session:
            mock_run_session.return_value = (Path("/tmp/session"), 0)
            cli.main(["run", "-p", "hi"])
            args, kwargs = mock_run_session.call_args
            self.assertEqual(args[0], ["-p", "hi"])

    def test_run_strips_leading_double_dash(self):
        with patch("claude_lens.cli.run_session") as mock_run_session:
            mock_run_session.return_value = (Path("/tmp/session"), 0)
            cli.main(["run", "--", "-p", "hi"])
            args, kwargs = mock_run_session.call_args
            self.assertEqual(args[0], ["-p", "hi"])

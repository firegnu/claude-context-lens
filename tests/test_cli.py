import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claude_lens import cli


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


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

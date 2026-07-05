import json
import tempfile
import unittest
from pathlib import Path

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

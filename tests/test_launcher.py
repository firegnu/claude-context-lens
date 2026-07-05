import json
import tempfile
import unittest
from pathlib import Path

from claude_lens import launcher


class BuildOtelEnvTest(unittest.TestCase):
    def test_sets_raw_bodies_file_target_without_mutating_base(self):
        base = {"PATH": "/usr/bin"}
        env = launcher.build_otel_env(Path("/tmp/raw"), base)
        self.assertEqual(env["OTEL_LOG_RAW_API_BODIES"], "file:/tmp/raw")
        self.assertEqual(env["OTEL_METRICS_EXPORTER"], "none")
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertNotIn("OTEL_LOG_RAW_API_BODIES", base)  # base untouched


class RunSessionTest(unittest.TestCase):
    def test_runs_then_ingests(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)

            def fake_runner(cmd, env):
                self.assertEqual(cmd[0], "claude")
                raw = Path(env["OTEL_LOG_RAW_API_BODIES"][len("file:"):])
                (raw / "a.request.json").write_text(
                    json.dumps({"model": "m", "messages": [{"role": "user", "content": "hi"}]}), encoding="utf-8")

            sd = launcher.run_session(
                ["-p", "hi"], session_id="20260101-000000",
                captured_at="2026-01-01T00:00:00Z", root=root,
                base_env={"PATH": "/usr/bin"}, runner=fake_runner)

            self.assertTrue((sd / "session.json").exists())
            self.assertEqual(sd, root / "20260101-000000")

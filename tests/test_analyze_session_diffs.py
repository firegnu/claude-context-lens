import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_session_diffs.py"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def request(messages):
    return {
        "model": "claude-test",
        "max_tokens": 100,
        "system": [{"type": "text", "text": "system"}],
        "messages": messages,
        "tools": [{"name": "Read", "description": "read", "input_schema": {}}],
    }


class AnalyzeSessionDiffsCliTest(unittest.TestCase):
    def test_reports_append_only_message_diff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_dir = root / "bodies"
            out_dir = root / "diffs"
            first = session_dir / "first.request.json"
            second = session_dir / "second.request.json"

            write_json(first, request([{"role": "user", "content": "hello"}]))
            write_json(
                second,
                request(
                    [
                        {"role": "user", "content": "hello"},
                        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
                        {"role": "user", "content": [{"type": "text", "text": "next"}]},
                    ]
                ),
            )
            order = root / "order.json"
            write_json(
                order,
                {
                    "ordered_requests": [
                        {"index": 1, "request_file": first.name, "inferred_response_file": None},
                        {"index": 2, "request_file": second.name, "inferred_response_file": None},
                    ]
                },
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--session-dir",
                    str(session_dir),
                    "--order",
                    str(order),
                    "--out",
                    str(out_dir),
                ],
                check=True,
            )

            manifest = json.loads((out_dir / "session_diff_manifest.json").read_text(encoding="utf-8"))
            second_diff = manifest["turn_diffs"][1]
            self.assertTrue(second_diff["messages"]["append_only"])
            self.assertEqual(second_diff["messages"]["common_prefix_count"], 1)
            self.assertEqual(second_diff["messages"]["added_count"], 2)
            self.assertEqual(second_diff["messages"]["added"][0]["role"], "assistant")
            self.assertFalse(second_diff["system"]["changed"])
            self.assertFalse(second_diff["tools"]["changed"])
            self.assertTrue((out_dir / "turns" / "0002.json").exists())
            self.assertTrue((out_dir / "timeline_diff.md").exists())


if __name__ == "__main__":
    unittest.main()

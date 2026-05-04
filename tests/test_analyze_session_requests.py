import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_session_requests.py"


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def request(messages_count, previous_message_id=None):
    return {
        "model": "claude-test",
        "diagnostics": {"previous_message_id": previous_message_id},
        "messages": [{"role": "user", "content": "x"} for _ in range(messages_count)],
        "tools": [],
    }


def response(message_id, stop_reason="end_turn"):
    return {
        "id": message_id,
        "model": "claude-test",
        "stop_reason": stop_reason,
        "content": [{"type": "text", "text": "ok"}],
    }


class AnalyzeSessionRequestsCliTest(unittest.TestCase):
    def test_orders_requests_by_logical_message_growth(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "bodies"
            out_dir = Path(temp_dir) / "analysis"
            session_dir.mkdir()

            write_json(session_dir / "third.request.json", request(5, "msg_b"))
            write_json(session_dir / "first.request.json", request(1))
            write_json(session_dir / "second.request.json", request(3, "msg_a"))
            write_json(session_dir / "response_a.response.json", response("msg_a", "tool_use"))
            write_json(session_dir / "response_b.response.json", response("msg_b", "end_turn"))

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--session-dir",
                    str(session_dir),
                    "--out",
                    str(out_dir),
                ],
                check=True,
            )

            manifest = json.loads((out_dir / "session_manifest.json").read_text(encoding="utf-8"))
            ordered = manifest["ordered_requests"]
            self.assertEqual([item["request_file"] for item in ordered], [
                "first.request.json",
                "second.request.json",
                "third.request.json",
            ])
            self.assertEqual(ordered[1]["previous_response_file"], "response_a.response.json")
            self.assertEqual(ordered[1]["confidence"], "high:linked")
            self.assertTrue((out_dir / "timeline.md").exists())


if __name__ == "__main__":
    unittest.main()

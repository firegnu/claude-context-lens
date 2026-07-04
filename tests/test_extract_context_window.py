import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract_context_window.py"


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


class ExtractContextWindowCliTest(unittest.TestCase):
    def write_sample_request(self, request_path):
        write_json(
            request_path,
            {
                "model": "claude-test",
                "max_tokens": 42,
                "stream": True,
                "system": [{"type": "text", "text": "system text"}],
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": "hello"}],
                    }
                ],
                "tools": [
                    {
                        "name": "Read",
                        "description": "read files",
                        "input_schema": {"type": "object"},
                    }
                ],
            },
        )

    def test_extracts_single_request_from_cli_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp = Path(temp_dir)
            request_path = tmp / "sample.request.json"
            response_path = tmp / "sample.response.json"
            out_path = tmp / "breakdown"

            self.write_sample_request(request_path)
            write_json(
                response_path,
                {
                    "id": "msg_test",
                    "model": "claude-test",
                    "stop_reason": "end_turn",
                    "usage": {"output_tokens": 3},
                    "content": [{"type": "text", "text": "hi"}],
                },
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                    "--out",
                    str(out_path),
                ],
                check=True,
            )

            manifest = json.loads((out_path / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_files"]["request"], str(request_path))
            self.assertEqual(manifest["source_files"]["response"], str(response_path))
            self.assertEqual(
                manifest["sections"][0]["file"],
                str(out_path / "01_system" / "00.md"),
            )
            self.assertEqual(manifest["totals"]["system_chars"], len("system text"))
            self.assertTrue((out_path / "02_messages" / "message_00_content_00.md").exists())
            self.assertTrue((out_path / "03_tools" / "00_Read.json").exists())
            self.assertTrue((out_path / "04_response" / "content_00.md").exists())

    def test_custom_request_does_not_use_default_response(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp = Path(temp_dir)
            request_path = tmp / "sample.request.json"
            out_path = tmp / "breakdown"
            self.write_sample_request(request_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--request",
                    str(request_path),
                    "--out",
                    str(out_path),
                ],
                check=True,
            )

            manifest = json.loads((out_path / "manifest.json").read_text(encoding="utf-8"))
            self.assertIsNone(manifest["source_files"]["response"])
            self.assertIsNone(manifest["response"])
            self.assertFalse((out_path / "04_response").exists())

    def test_tool_result_content_is_rendered_as_decoded_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp = Path(temp_dir)
            request_path = tmp / "sample.request.json"
            out_path = tmp / "breakdown"

            write_json(
                request_path,
                {
                    "model": "claude-test",
                    "max_tokens": 42,
                    "stream": True,
                    "system": [],
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "toolu_123",
                                    "content": "\u001b[1mMakefile\u001b[0m\nREADME.md\nsrc",
                                    "is_error": False,
                                }
                            ],
                        }
                    ],
                    "tools": [],
                },
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--request",
                    str(request_path),
                    "--out",
                    str(out_path),
                ],
                check=True,
            )

            rendered = (out_path / "02_messages" / "message_00_content_00.md").read_text(encoding="utf-8")
            self.assertIn("- tool_use_id: `toolu_123`", rendered)
            self.assertIn("Makefile\nREADME.md\nsrc", rendered)
            self.assertNotIn("\\u001b", rendered)
            self.assertNotIn('"content"', rendered)


if __name__ == "__main__":
    unittest.main()

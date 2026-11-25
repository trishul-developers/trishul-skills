import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import agy_wsl_headless as awh  # noqa: E402


class AgyWslHeadlessTests(unittest.TestCase):
    def test_windows_to_wsl_path(self):
        self.assertEqual(awh.windows_to_wsl_path(r"E:\Projects\trishul-tactical-engine"), "/mnt/e/Projects/trishul-tactical-engine")
        self.assertEqual(awh.windows_to_wsl_path("C:/Users/tosum/file.md"), "/mnt/c/Users/tosum/file.md")
        self.assertEqual(awh.windows_to_wsl_path("/tmp/work"), "/tmp/work")

    def test_swarm_defaults_in_dispatch_script(self):
        args = awh.parse_args(["--swarm", "-C", r"E:\Projects\demo", "Run swarm"])
        script = awh.build_dispatch_script(args, "/mnt/c/tmp/prompt.md", "/mnt/e/Projects/demo")
        self.assertIn("cd /mnt/e/Projects/demo", script)
        self.assertIn("--dangerously-skip-permissions", script)
        self.assertIn("--print-timeout 300s", script)
        self.assertIn("PROMPT_TEXT=$(cat /mnt/c/tmp/prompt.md)", script)
        self.assertIn('agy -p="$PROMPT_TEXT"', script)

    def test_dry_run_preserves_nested_quotes_in_prompt_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "run"
            prompt = 'Call swarm(action="title", title="test") and reply \'OK\'.'
            rc = awh.main([
                "--swarm",
                "--print-timeout", "120s",
                "-C", "/tmp",
                "--out-dir", str(out_dir),
                "--dry-run",
                prompt,
            ])
            self.assertEqual(rc, 0)
            self.assertEqual((out_dir / "prompt.md").read_text(encoding="utf-8"), prompt)
            dispatch = (out_dir / "dispatch.sh").read_text(encoding="utf-8")
            self.assertIn("cd /tmp", dispatch)
            self.assertIn("--print-timeout 120s", dispatch)

    def _run_mocked(self, extra, stdout=b""):
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"], captured["kw"] = cmd, kw
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr=b"")

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "run"
            with mock.patch.object(awh.subprocess, "run", fake_run):
                rc = awh.main(["--out-dir", str(out_dir), *extra])
            result = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
            prompt = (out_dir / "prompt.md").read_bytes()
        return rc, captured, result, prompt

    def test_stdin_is_lf_bytes_without_carriage_returns(self):
        rc, cap, _, _ = self._run_mocked(["-C", "/tmp", "hi"])
        self.assertEqual(rc, 0)
        data = cap["kw"]["input"]
        self.assertIsInstance(data, bytes)
        self.assertNotIn(b"\r", data)
        self.assertIn(b"set -euo pipefail\n", data)
        self.assertFalse(cap["kw"].get("text"))

    def test_json_output_reports_conversation_id_and_usage(self):
        payload = json.dumps({"response": "réponse", "conversation_id": "abc-123", "status": "SUCCESS", "usage": {"in": 1}})
        rc, _, result, _ = self._run_mocked(["--output-format", "json", "-C", "/tmp", "hi"], stdout=payload.encode("utf-8"))
        self.assertEqual(rc, 0)
        self.assertEqual(result["conversation_id"], "abc-123")
        self.assertEqual(result["usage"], {"in": 1})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["conversation_id"], "abc-123")

    def test_exit_zero_with_error_status_and_no_response_is_failed(self):
        err = json.dumps({"conversation_id": "c1", "status": "ERROR", "response": "", "error": "boom"})
        rc, _, result, _ = self._run_mocked(["--output-format", "json", "-C", "/tmp", "hi"], stdout=err.encode("utf-8"))
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["agy_status"], "ERROR")
        # no response key at all must not fall back to the raw JSON text
        rc, _, result, _ = self._run_mocked(["--output-format", "json", "-C", "/tmp", "hi"],
                                            stdout=json.dumps({"status": "ERROR"}).encode("utf-8"))
        self.assertEqual((rc, result["status"]), (1, "failed"))

    def test_non_success_status_with_response_or_success_without_response(self):
        part = json.dumps({"status": "ERROR", "response": "partial answer"})
        rc, _, result, _ = self._run_mocked(["--output-format", "json", "-C", "/tmp", "hi"], stdout=part.encode("utf-8"))
        self.assertEqual((rc, result["status"]), (0, "ok"))
        empty_ok = json.dumps({"status": "SUCCESS", "response": ""})
        rc, _, result, _ = self._run_mocked(["--output-format", "json", "-C", "/tmp", "hi"], stdout=empty_ok.encode("utf-8"))
        self.assertEqual((rc, result["status"]), (0, "ok"))
        # text output keeps the plain exit-code rule
        rc, _, result, _ = self._run_mocked(["-C", "/tmp", "hi"], stdout=b"")
        self.assertEqual((rc, result["status"]), (0, "ok"))

    def test_env_note_only_for_windows_mounts(self):
        _, _, _, mnt = self._run_mocked(["-C", r"E:\Projects\demo", "hi"])
        self.assertIn(b"git.exe", mnt)
        self.assertIn(b"dotnet.exe", mnt)
        self.assertIn(b"</dev/null", mnt)
        self.assertNotIn(b"\r", mnt)
        _, _, _, plain = self._run_mocked(["-C", "/tmp", "hi"])
        self.assertEqual(plain, b"hi")
        _, _, _, off = self._run_mocked(["--no-env-note", "-C", r"E:\Projects\demo", "hi"])
        self.assertEqual(off, b"hi")


if __name__ == "__main__":
    unittest.main()

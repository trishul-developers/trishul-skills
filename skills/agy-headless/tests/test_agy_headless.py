import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import agy_headless as ah  # noqa: E402


class AgyHeadlessTests(unittest.TestCase):
    def _run_mocked(self, extra_args, stdout_bytes=b""):
        captured = {}

        class FakeProc:
            returncode = 0
            pid = 1234

            def wait(self, timeout=None):
                return 0

        def fake_popen(cmd, **kw):
            captured["cmd"] = cmd
            kw["stdout"].write(stdout_bytes)
            return FakeProc()

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "run"
            with mock.patch.object(ah.shutil, "which", return_value="agy"), \
                 mock.patch.object(ah.subprocess, "Popen", fake_popen), \
                 mock.patch.object(sys, "argv", [
                     "agy_headless.py",
                     "--out-dir", str(out_dir),
                     *extra_args,
                 ]):
                rc = ah.main()
            result = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
        return rc, captured, result

    def test_json_error_status_fails_even_with_exit_zero(self):
        payload = json.dumps({"status": "ERROR", "response": "partial"})
        rc, _, result = self._run_mocked(["--output-format", "json", "hi"], stdout_bytes=payload.encode("utf-8"))
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["agy_status"], "ERROR")

    def test_json_null_response_handled_safely(self):
        payload = json.dumps({"status": "SUCCESS", "response": None})
        rc, _, result = self._run_mocked(["--output-format", "json", "hi"], stdout_bytes=payload.encode("utf-8"))
        self.assertEqual(rc, 0)
        self.assertEqual(result["status"], "success")

        payload_err = json.dumps({"response": None})
        rc2, _, result2 = self._run_mocked(["--output-format", "json", "hi"], stdout_bytes=payload_err.encode("utf-8"))
        self.assertEqual(rc2, 1)
        self.assertEqual(result2["status"], "error")

    def test_dry_run_long_prompt_adds_out_dir_and_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "run"
            prompt_file = Path(tmp) / "long.md"
            prompt_file.write_text("z" * (ah.MAX_INLINE_CHARS + 5), encoding="utf-8")
            with mock.patch.object(sys, "argv", [
                "agy_headless.py",
                "--out-dir", str(out_dir),
                "--print-timeout", "90s",
                "--disable-slash-commands",
                "--dry-run",
                "--prompt-file", str(prompt_file),
            ]):
                rc = ah.main()
            self.assertEqual(rc, 0)
            self.assertTrue((out_dir / "prompt.md").is_file())


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import claude_headless as ch  # noqa: E402


class ClaudeHeadlessTests(unittest.TestCase):
    def test_double_dash_separates_variadic_flags_from_prompt(self):
        ns = SimpleNamespace(
            model="claude-sonnet-5-5",
            effort="high",
            output_format="json",
            dangerously_skip_permissions=False,
            allowed_tools="Read,Edit",
            tools="Read,Edit,Bash",
            system_prompt=None,
            system_prompt_file=None,
            append_system_prompt=None,
            append_system_prompt_file=None,
            add_dir=None,
            bare=False,
            resume=None,
            continue_last=False,
            json_schema=None,
        )
        cmd = ch.build_command(ns, "claude", "Summarize repo")
        self.assertIn("--effort", cmd)
        self.assertEqual(cmd[cmd.index("--effort") + 1], "high")
        self.assertEqual(cmd[-2:], ["--", "Summarize repo"])

    def test_dry_run_and_long_prompt_uses_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "run"
            prompt_file = Path(tmp) / "long.md"
            long_text = "x" * (ch.MAX_INLINE_CHARS + 50)
            prompt_file.write_text(long_text, encoding="utf-8")

            with mock.patch.object(sys, "argv", [
                "claude_headless.py",
                "--out-dir", str(out_dir),
                "--allowed-tools", "Read",
                "--effort", "medium",
                "--dry-run",
                "--prompt-file", str(prompt_file),
            ]):
                rc = ch.main()
            self.assertEqual(rc, 0)
            self.assertEqual((out_dir / "prompt.md").read_text(encoding="utf-8"), long_text)

    def test_long_prompt_pipes_via_stdin_in_popen(self):
        captured = {}

        class FakeProc:
            returncode = 0
            pid = 1234

            def communicate(self, input=None, timeout=None):
                captured["input"] = input
                return (b"", b"")

            def wait(self, timeout=None):
                return 0

        def fake_popen(cmd, **kw):
            captured["cmd"] = cmd
            captured["kw"] = kw
            kw["stdout"].write(json.dumps({"result": "ok", "session_id": "s1"}).encode("utf-8"))
            return FakeProc()

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "run"
            prompt_file = Path(tmp) / "long.md"
            long_text = "y" * (ch.MAX_INLINE_CHARS + 10)
            prompt_file.write_text(long_text, encoding="utf-8")

            with mock.patch.object(ch.shutil, "which", return_value="claude"), \
                 mock.patch.object(ch.subprocess, "Popen", fake_popen), \
                 mock.patch.object(sys, "argv", [
                     "claude_headless.py",
                     "--out-dir", str(out_dir),
                     "--prompt-file", str(prompt_file),
                 ]):
                rc = ch.main()
            self.assertEqual(rc, 0)
            self.assertNotIn(long_text, captured["cmd"])
            self.assertEqual(captured["kw"]["stdin"], subprocess.PIPE)
            self.assertEqual(captured["input"], long_text.encode("utf-8"))

    def test_json_is_error_and_null_result_guards(self):
        for raw, expected_rc, expected_status in [
            (json.dumps({"is_error": True, "result": None}), 1, "error"),
            (json.dumps(["not", "a", "dict"]), 0, "success"),
        ]:
            class FakeProc:
                returncode = 0
                pid = 1234

                def wait(self, timeout=None):
                    return 0

            def fake_popen(cmd, **kw):
                kw["stdout"].write(raw.encode("utf-8"))
                return FakeProc()

            with tempfile.TemporaryDirectory() as tmp:
                out_dir = Path(tmp) / "run"
                with mock.patch.object(ch.shutil, "which", return_value="claude"), \
                     mock.patch.object(ch.subprocess, "Popen", fake_popen), \
                     mock.patch.object(sys, "argv", [
                         "claude_headless.py",
                         "--out-dir", str(out_dir),
                         "hi",
                     ]):
                    rc = ch.main()
                result = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
                self.assertEqual(rc, expected_rc)
                self.assertEqual(result["status"], expected_status)


if __name__ == "__main__":
    unittest.main()

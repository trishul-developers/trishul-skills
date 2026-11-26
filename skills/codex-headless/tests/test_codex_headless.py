import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import codex_headless as cxh  # noqa: E402


class CodexHeadlessTests(unittest.TestCase):
    def test_resume_places_add_dir_and_cd_before_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            extra = Path(tmp) / "extra"
            extra.mkdir()
            ns = SimpleNamespace(
                resume="thread-123",
                fork=None,
                sandbox="workspace-write",
                add_dir=[str(extra)],
                model="gpt-6.2-sol",
                effort="high",
                config=None,
                worktree=False,
                image=None,
                output_schema=None,
                dangerously_bypass=False,
                ephemeral=False,
            )
            with mock.patch.object(cxh, "is_git_repo", return_value=True):
                cmd = cxh.build_command(ns, "codex", cwd, cwd / "last_message.md")
            resume_idx = cmd.index("resume")
            add_dir_idx = cmd.index("--add-dir")
            cd_idx = cmd.index("-C")
            self.assertLess(cd_idx, resume_idx)
            self.assertLess(add_dir_idx, resume_idx)

    def test_dry_run_exits_zero_and_saves_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "run"
            with mock.patch.object(sys, "argv", [
                "codex_headless.py",
                "-C", tmp,
                "--out-dir", str(out_dir),
                "--dry-run",
                "Test dry run",
            ]):
                rc = cxh.main()
            self.assertEqual(rc, 0)
            self.assertEqual((out_dir / "prompt.md").read_text(encoding="utf-8"), "Test dry run")


if __name__ == "__main__":
    unittest.main()

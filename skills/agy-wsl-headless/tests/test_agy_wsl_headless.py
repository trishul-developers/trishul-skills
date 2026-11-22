import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()

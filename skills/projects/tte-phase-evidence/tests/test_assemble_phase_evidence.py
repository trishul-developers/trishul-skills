import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import assemble_phase_evidence as ape  # noqa: E402


class TestAssemblePhaseEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        (self.repo / "README.md").write_text("init\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=self.repo, check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolve_phase_base_tag_and_step_table_pipe_escape(self):
        subprocess.run(["git", "tag", "G02-base"], cwd=self.repo, check=True)
        (self.repo / "README.md").write_text("step1\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: add A | B"], cwd=self.repo, check=True, capture_output=True)

        base_ref = ape.resolve_base_ref(self.repo, "G02", None)
        self.assertEqual(base_ref, "G02-base")
        steps = ape.get_step_table(self.repo, base_ref)
        self.assertEqual(len(steps), 1)
        md = ape.format_evidence_package("G02", base_ref, self.repo, steps, "none", "ok", True, [])
        self.assertIn("feat: add A \\| B", md)

    def test_get_step_table_fails_on_invalid_ref(self):
        with self.assertRaises(RuntimeError):
            ape.get_step_table(self.repo, "nonexistent-ref")

    def test_phase_scoped_red_list_markdown_table(self):
        plan_dir = self.repo / "docs" / "implementation" / "plan_v2"
        plan_dir.mkdir(parents=True)
        (plan_dir / "g01_temporary_red_list.md").write_text("- old item\n", encoding="utf-8")
        (plan_dir / "g02_temporary_red_list.md").write_text(
            "| Test | Reason |\n|---|---|\n| MyTest | Pending |\n",
            encoding="utf-8",
        )
        findings_g01 = ape.check_preconditions(self.repo, phase="G01")
        self.assertEqual(len(findings_g01), 1)
        self.assertIn("g01_temporary_red_list.md", findings_g01[0])

        findings_g02 = ape.check_preconditions(self.repo, phase="G02")
        self.assertEqual(len(findings_g02), 1)
        self.assertIn("g02_temporary_red_list.md", findings_g02[0])
        self.assertIn("1 entries remaining", findings_g02[0])


if __name__ == "__main__":
    unittest.main()

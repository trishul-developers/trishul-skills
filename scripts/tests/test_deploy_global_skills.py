import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import deploy_global_skills as dgs  # noqa: E402


class DeploySkillsTests(unittest.TestCase):
    def test_cross_agent_headless_rule(self):
        self.assertNotIn("claude-headless", dgs.PROVIDER_SKILLS["claude"])
        self.assertIn("codex-headless", dgs.PROVIDER_SKILLS["claude"])
        self.assertIn("agy-headless", dgs.PROVIDER_SKILLS["claude"])

        self.assertNotIn("codex-headless", dgs.PROVIDER_SKILLS["codex"])
        self.assertIn("claude-headless", dgs.PROVIDER_SKILLS["codex"])
        self.assertIn("agy-headless", dgs.PROVIDER_SKILLS["codex"])
        self.assertIn("agent-delivery", dgs.PROVIDER_SKILLS["codex"])
        self.assertIn("github-pr-workflow", dgs.PROVIDER_SKILLS["codex"])
        self.assertIn("unity-pipeline", dgs.PROVIDER_SKILLS["codex"])

        self.assertNotIn("agy-headless", dgs.PROVIDER_SKILLS["antigravity"])
        self.assertIn("claude-headless", dgs.PROVIDER_SKILLS["antigravity"])
        self.assertIn("codex-headless", dgs.PROVIDER_SKILLS["antigravity"])

    def test_project_local_selective_install_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            existing = proj / ".claude" / "skills" / "custom-skill"
            existing.mkdir(parents=True)
            (existing / "SKILL.md").write_text("# custom", encoding="utf-8")

            rc = dgs.main(["--project", str(proj), "--skill", "unity-pipeline", "--agent", "claude"])
            self.assertEqual(rc, 0)
            self.assertTrue((proj / ".claude" / "skills" / "unity-pipeline" / "SKILL.md").is_file())
            self.assertTrue((existing / "SKILL.md").is_file())
            self.assertFalse((proj / ".agents").exists())

    def test_project_local_all_agents_installs_claude_and_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            rc = dgs.main(["--project", str(proj), "--agent", "all"])
            self.assertEqual(rc, 0)
            self.assertFalse((proj / ".claude" / "skills" / "claude-headless").exists())
            self.assertTrue((proj / ".claude" / "skills" / "codex-headless" / "SKILL.md").is_file())
            self.assertTrue((proj / ".agents" / "skills" / "unity-pipeline" / "SKILL.md").is_file())
            self.assertTrue((proj / ".agents" / "skills" / "claude-headless" / "SKILL.md").is_file())

    def test_clean_removes_self_headless_and_preserves_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            agy_dir = Path(tmp) / "agy"
            (agy_dir / "agy-headless").mkdir(parents=True)
            (agy_dir / "state").mkdir(parents=True)
            (agy_dir / "state" / "keep.json").write_text("{}", encoding="utf-8")

            dgs.deploy_to_target(
                label="antigravity",
                agent_key="antigravity",
                target_dir=agy_dir,
                skills=dgs.PROVIDER_SKILLS["antigravity"],
                clean=True,
                dry_run=False,
            )
            self.assertFalse((agy_dir / "agy-headless").exists())
            self.assertTrue((agy_dir / "state" / "keep.json").is_file())
            self.assertTrue((agy_dir / "codex-headless" / "SKILL.md").is_file())

    def test_dry_run_makes_no_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            rc = dgs.main(["--project", str(proj), "--skill", "unity-pipeline", "--agent", "claude", "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertFalse((proj / ".claude").exists())


if __name__ == "__main__":
    unittest.main()

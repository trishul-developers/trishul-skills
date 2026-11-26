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

        self.assertNotIn("codex-headless", dgs.PROVIDER_SKILLS["agents"])
        self.assertNotIn("agy-headless", dgs.PROVIDER_SKILLS["agents"])
        self.assertNotIn("agy-wsl-headless", dgs.PROVIDER_SKILLS["agents"])
        self.assertIn("claude-headless", dgs.PROVIDER_SKILLS["agents"])

    def test_quota_skills_included_in_platform_and_managed(self):
        for skill in ("agy-quota", "codex-quota"):
            self.assertIn(skill, dgs.PLATFORM_SKILL_NAMES)
            self.assertIn(skill, dgs.ALL_MANAGED_GLOBAL_SKILLS)
            for agent in ("claude", "codex", "antigravity", "opencode", "agents"):
                self.assertIn(skill, dgs.PROVIDER_SKILLS[agent])

    def test_copy_skill_preserves_fixture_logs_and_skips_other_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            rc = dgs.main(["--project", str(proj), "--skill", "github-pr-workflow", "--agent", "claude"])
            self.assertEqual(rc, 0)
            fixture_log = proj / ".claude" / "skills" / "github-pr-workflow" / "tests" / "fixtures" / "sample_tte_ci.log"
            self.assertTrue(fixture_log.is_file())

            src = Path(tmp) / "src_skill"
            dest = Path(tmp) / "dest_skill"
            (src / "tests" / "fixtures").mkdir(parents=True)
            (src / "tests" / "fixtures" / "sample.log").write_text("keep", encoding="utf-8")
            (src / "debug.log").write_text("skip", encoding="utf-8")
            dgs.copy_skill(src, dest)
            self.assertTrue((dest / "tests" / "fixtures" / "sample.log").is_file())
            self.assertFalse((dest / "debug.log").exists())

    def test_unknown_skill_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            rc = dgs.main(["--project", str(proj), "--skill", "nonexistent-skill-xyz", "--agent", "claude"])
            self.assertNotEqual(rc, 0)
            self.assertFalse((proj / ".claude" / "skills" / "nonexistent-skill-xyz").exists())

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

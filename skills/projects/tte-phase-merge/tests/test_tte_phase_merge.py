#!/usr/bin/env python3
"""Unit tests for tte_phase_merge.py using real temporary Git repositories."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import tte_phase_merge  # noqa: E402


def run_git(args, cwd):
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class TestTtePhaseMergeRealGit(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

        # Initialize real git repository
        run_git(["init", "-b", "phase-test"], self.repo_dir)
        run_git(["config", "user.name", "TTE Tester"], self.repo_dir)
        run_git(["config", "user.email", "tester@trishul.local"], self.repo_dir)
        run_git(["config", "commit.gpgSign", "false"], self.repo_dir)

        # Create initial commit on phase-test
        (self.repo_dir / "README.md").write_text("# Phase Repo\n", encoding="utf-8")
        run_git(["add", "README.md"], self.repo_dir)
        run_git(["commit", "-m", "Initial commit on phase-test"], self.repo_dir)

        # Create side branch with one commit
        run_git(["checkout", "-b", "side-feature"], self.repo_dir)
        (self.repo_dir / "feature.txt").write_text("New feature\n", encoding="utf-8")
        run_git(["add", "feature.txt"], self.repo_dir)
        run_git(["commit", "-m", "Add feature"], self.repo_dir)

        # Return to phase-test
        run_git(["checkout", "phase-test"], self.repo_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_refuse_main_and_hyphen_branch(self):
        # Refuse names starting with '-'
        ret = tte_phase_merge.execute_phase_merge("-flag", "phase-test", project_dir=self.repo_dir)
        self.assertEqual(ret, 1)

        # Refuse 'main'
        ret = tte_phase_merge.execute_phase_merge("main", "phase-test", project_dir=self.repo_dir)
        self.assertEqual(ret, 1)

        ret = tte_phase_merge.execute_phase_merge("side-feature", "main", project_dir=self.repo_dir)
        self.assertEqual(ret, 1)

        # Create a branch named origin/main to test symbolic ref resolution
        run_git(["branch", "origin/main"], self.repo_dir)
        ret = tte_phase_merge.execute_phase_merge("origin/main", "phase-test", project_dir=self.repo_dir)
        self.assertEqual(ret, 1)

    def test_refuse_dirty_working_tree(self):
        # Make working tree dirty
        (self.repo_dir / "dirty.txt").write_text("Uncommitted changes\n", encoding="utf-8")
        run_git(["add", "dirty.txt"], self.repo_dir)

        ret = tte_phase_merge.execute_phase_merge("side-feature", "phase-test", project_dir=self.repo_dir)
        self.assertEqual(ret, 1)

    def test_refuse_project_settings_without_flag(self):
        # Create branch with ProjectSettings change
        run_git(["checkout", "-b", "touch-settings"], self.repo_dir)
        ps_dir = self.repo_dir / "ProjectSettings"
        ps_dir.mkdir(parents=True, exist_ok=True)
        (ps_dir / "ProjectSettings.asset").write_text("settings: modified\n", encoding="utf-8")
        run_git(["add", "ProjectSettings/ProjectSettings.asset"], self.repo_dir)
        run_git(["commit", "-m", "Modify settings"], self.repo_dir)
        run_git(["checkout", "phase-test"], self.repo_dir)

        ret = tte_phase_merge.execute_phase_merge(
            "touch-settings", "phase-test", allow_settings=False, project_dir=self.repo_dir
        )
        self.assertEqual(ret, 1)

        # Should succeed if allow_settings is True
        ret_ok = tte_phase_merge.execute_phase_merge(
            "touch-settings", "phase-test", allow_settings=True, push=False, project_dir=self.repo_dir
        )
        self.assertEqual(ret_ok, 0)
        self.assertTrue((self.repo_dir / "ProjectSettings" / "ProjectSettings.asset").exists())

    def test_already_merged(self):
        # Perform merge first
        ret = tte_phase_merge.execute_phase_merge(
            "side-feature", "phase-test", push=False, project_dir=self.repo_dir
        )
        self.assertEqual(ret, 0)

        # Try merging side-feature again: should report already merged and return 0 without error
        ret_again = tte_phase_merge.execute_phase_merge(
            "side-feature", "phase-test", push=False, project_dir=self.repo_dir
        )
        self.assertEqual(ret_again, 0)

    def test_conflict_aborted_and_tree_clean(self):
        # Create conflict
        (self.repo_dir / "conflict.txt").write_text("Phase version\n", encoding="utf-8")
        run_git(["add", "conflict.txt"], self.repo_dir)
        run_git(["commit", "-m", "Phase conflict base"], self.repo_dir)

        run_git(["checkout", "-b", "conflict-side", "HEAD~1"], self.repo_dir)
        (self.repo_dir / "conflict.txt").write_text("Side branch version\n", encoding="utf-8")
        run_git(["add", "conflict.txt"], self.repo_dir)
        run_git(["commit", "-m", "Side conflict version"], self.repo_dir)

        run_git(["checkout", "phase-test"], self.repo_dir)

        # Merge should fail with conflict code 2, abort merge, and leave tree clean
        ret = tte_phase_merge.execute_phase_merge(
            "conflict-side", "phase-test", push=False, project_dir=self.repo_dir
        )
        self.assertEqual(ret, 2)

        # Tree must be clean after abort
        clean, _ = tte_phase_merge.is_working_tree_clean(self.repo_dir)
        self.assertTrue(clean)

    def test_dry_run_leaves_checked_out_branch_unchanged(self):
        # Checkout side-feature branch
        run_git(["checkout", "side-feature"], self.repo_dir)
        self.assertEqual(tte_phase_merge.get_current_branch(self.repo_dir), "side-feature")

        # Run dry-run against phase-test
        ret = tte_phase_merge.execute_phase_merge(
            "side-feature", "phase-test", dry_run=True, project_dir=self.repo_dir
        )
        self.assertEqual(ret, 0)

        # Checked out branch MUST still be side-feature (dry-run changed nothing)
        self.assertEqual(tte_phase_merge.get_current_branch(self.repo_dir), "side-feature")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Unit tests for tte_phase_merge.py using mock git and gh fixtures."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import tte_phase_merge  # noqa: E402


class TestTtePhaseMerge(unittest.TestCase):
    def test_refuse_main_branch(self):
        ret = tte_phase_merge.execute_phase_merge("main", "g02-phase")
        self.assertEqual(ret, 1)

        ret = tte_phase_merge.execute_phase_merge("side-branch", "main")
        self.assertEqual(ret, 1)

    def test_refuse_same_branch(self):
        ret = tte_phase_merge.execute_phase_merge("g02-phase", "g02-phase")
        self.assertEqual(ret, 1)

    @patch("tte_phase_merge.is_working_tree_clean")
    def test_refuse_dirty_working_tree(self, mock_clean):
        mock_clean.return_value = (False, " M Assets/Scripts/Foo.cs")
        ret = tte_phase_merge.execute_phase_merge("side-branch", "g02-phase")
        self.assertEqual(ret, 1)

    @patch("tte_phase_merge.is_working_tree_clean")
    @patch("tte_phase_merge.get_current_branch")
    @patch("tte_phase_merge.compute_merge_base")
    @patch("tte_phase_merge.get_changed_files")
    def test_refuse_project_settings_without_flag(self, mock_changed, mock_mb, mock_branch, mock_clean):
        mock_clean.return_value = (True, "")
        mock_branch.return_value = "g02-phase"
        mock_mb.return_value = "1234567890abcdef"
        mock_changed.return_value = [
            "Assets/Scripts/Normal.cs",
            "ProjectSettings/ProjectSettings.asset",
        ]

        ret = tte_phase_merge.execute_phase_merge("side-branch", "g02-phase", allow_settings=False)
        self.assertEqual(ret, 1)

    @patch("tte_phase_merge.is_working_tree_clean")
    @patch("tte_phase_merge.get_current_branch")
    @patch("tte_phase_merge.compute_merge_base")
    @patch("tte_phase_merge.get_changed_files")
    @patch("tte_phase_merge.run_cmd")
    def test_allow_project_settings_with_flag(self, mock_run, mock_changed, mock_mb, mock_branch, mock_clean):
        mock_clean.return_value = (True, "")
        mock_branch.return_value = "g02-phase"
        mock_mb.return_value = "1234567890abcdef"
        mock_changed.return_value = [
            "ProjectSettings/ProjectSettings.asset",
            "Packages/packages-lock.json",
        ]
        # mock git merge --no-ff and git rev-parse HEAD
        def fake_run(cmd, cwd=None, timeout=60):
            cmd_str = " ".join(cmd)
            if "merge --no-ff" in cmd_str:
                return (0, "Merge made by recursive.", "")
            if "rev-parse HEAD" in cmd_str:
                return (0, "abcdef1234567890", "")
            return (0, "", "")

        mock_run.side_effect = fake_run

        ret = tte_phase_merge.execute_phase_merge("side-branch", "g02-phase", allow_settings=True, push=False)
        self.assertEqual(ret, 0)

    @patch("tte_phase_merge.is_working_tree_clean")
    @patch("tte_phase_merge.get_current_branch")
    @patch("tte_phase_merge.compute_merge_base")
    @patch("tte_phase_merge.get_changed_files")
    def test_dry_run_mode(self, mock_changed, mock_mb, mock_branch, mock_clean):
        mock_clean.return_value = (True, "")
        mock_branch.return_value = "g02-phase"
        mock_mb.return_value = "1234567890abcdef"
        mock_changed.return_value = ["Assets/Scripts/Normal.cs"]

        ret = tte_phase_merge.execute_phase_merge("side-branch", "g02-phase", dry_run=True)
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()

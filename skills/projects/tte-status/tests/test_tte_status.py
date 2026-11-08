#!/usr/bin/env python3
"""Unit tests for tte_status.py using canned git and gh fixtures."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import tte_status  # noqa: E402


CANNED_WORKTREE_PORCELAIN = """worktree E:/Projects/trishul-tactical-engine
HEAD 1234567890abcdef1234567890abcdef12345678
branch refs/heads/main

worktree E:/Projects/worktree-side
HEAD abcdef1234567890abcdef1234567890abcdef12
branch refs/heads/side-branch

worktree E:/Projects/worktree-detached
HEAD fedcba0987654321fedcba0987654321fedcba09
detached
"""

CANNED_FOR_EACH_REF = """origin/main|1234567|10 minutes ago
origin/side-branch|abcdef1|1 hour ago
origin/HEAD|1234567|10 minutes ago
origin|1234567|10 minutes ago
origin/old-branch|9999999|2 days ago
"""

CANNED_PR_LIST = json.dumps([
    {"number": 61, "headRefName": "g02-presentation-orders-ux", "title": "G02 Phase UX", "isDraft": True},
    {"number": 75, "headRefName": "g02-q36-stale-target", "title": "Fix stale doctrine", "isDraft": False},
])

CANNED_RUN_LIST = json.dumps([
    {
        "databaseId": 42333265082,
        "headSha": "5608c63e59eb1a9d504a0cd51378b545adf11b1e",
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/owner/repo/actions/runs/42333265082",
    }
])

CANNED_RUN_VIEW = json.dumps({
    "jobs": [
        {"name": "Fast C# compile gate", "conclusion": "success", "status": "completed"},
        {"name": "Unity EditMode", "conclusion": "success", "status": "completed"},
        {"name": "Unity PlayMode", "conclusion": "success", "status": "completed"},
    ]
})

CANNED_COMMENTS = json.dumps({
    "comments": [
        {"author": {"login": "user1"}, "createdAt": "2026-11-07T01:00:00Z", "body": "Comment 1 text"},
        {"author": {"login": "user2"}, "createdAt": "2026-11-07T02:00:00Z", "body": "Comment 2 text"},
        {"author": {"login": "user3"}, "createdAt": "2026-11-07T03:00:00Z", "body": "Comment 3 " + ("A" * 300)},
    ]
})


class TestTteStatus(unittest.TestCase):
    @patch("tte_status.run_cmd")
    def test_get_local_worktrees(self, mock_run):
        mock_run.return_value = (0, CANNED_WORKTREE_PORCELAIN, "")
        wts = tte_status.get_local_worktrees()
        self.assertEqual(len(wts), 3)
        self.assertEqual(wts[0]["branch"], "main")
        self.assertEqual(wts[1]["branch"], "side-branch")
        self.assertEqual(wts[2]["branch"], "(detached)")

    @patch("tte_status.run_cmd")
    def test_get_top_remote_branches(self, mock_run):
        mock_run.return_value = (0, CANNED_FOR_EACH_REF, "")
        branches = tte_status.get_top_remote_branches(count=5)
        # origin and origin/HEAD must be excluded
        names = [b[0] for b in branches]
        self.assertIn("origin/main", names)
        self.assertIn("origin/side-branch", names)
        self.assertIn("origin/old-branch", names)
        self.assertNotIn("origin", names)
        self.assertNotIn("origin/HEAD", names)

    @patch("tte_status.run_cmd")
    def test_get_open_prs(self, mock_run):
        mock_run.return_value = (0, CANNED_PR_LIST, "")
        prs = tte_status.get_open_prs("owner/repo")
        self.assertEqual(len(prs), 2)
        self.assertEqual(prs[0]["number"], 61)
        self.assertTrue(prs[0]["isDraft"])

    @patch("tte_status.run_cmd")
    def test_get_recent_comments(self, mock_run):
        mock_run.return_value = (0, CANNED_COMMENTS, "")
        comments = tte_status.get_recent_comments("owner/repo", "pr", 61, count=3)
        self.assertEqual(len(comments), 3)
        # Verify ~200 char truncation on long comment
        self.assertTrue(len(comments[2]["body"]) <= 205)
        self.assertTrue(comments[2]["body"].endswith("..."))

    @patch("tte_status.run_cmd")
    def test_format_status_under_60_lines(self, mock_run):
        def fake_run(cmd, cwd=None, timeout=30):
            cmd_str = " ".join(cmd)
            if "remote get-url" in cmd_str:
                return (0, "https://github.com/owner/repo.git", "")
            if "rev-parse" in cmd_str:
                return (0, "5608c63e59eb1a9d504a0cd51378b545adf11b1e", "")
            if "run list" in cmd_str:
                return (0, CANNED_RUN_LIST, "")
            if "run view" in cmd_str:
                return (0, CANNED_RUN_VIEW, "")
            if "rev-list" in cmd_str:
                return (0, "6 146", "")
            if "pr list" in cmd_str:
                return (0, CANNED_PR_LIST, "")
            if "for-each-ref" in cmd_str:
                return (0, CANNED_FOR_EACH_REF, "")
            if "view" in cmd_str and "comments" in cmd_str:
                return (0, CANNED_COMMENTS, "")
            if "worktree list" in cmd_str:
                return (0, CANNED_WORKTREE_PORCELAIN, "")
            return (0, "", "")

        mock_run.side_effect = fake_run
        output = tte_status.format_status(
            repo="owner/repo",
            phase_branch="g02-presentation-orders-ux",
            pr_num=61,
            issue_num=64,
        )
        lines = output.splitlines()
        self.assertLessEqual(len(lines), 60)
        self.assertIn("=== TTE Project Status: owner/repo ===", lines[0])
        self.assertIn("Phase: g02-presentation-orders-ux", output)
        self.assertIn("Run #42333265082", output)
        self.assertIn("Open PRs (2):", output)


if __name__ == "__main__":
    unittest.main()

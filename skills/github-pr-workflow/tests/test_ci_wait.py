#!/usr/bin/env python3
"""Unit tests for 'gh_helper.py ci wait': quiet CI run polling, waiting, and digest reporting."""

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import gh_helper  # noqa: E402


class TestCiWait(unittest.TestCase):
    def setUp(self):
        self.repo = "tosumitdhaka/trishul-tactical-engine"

    def test_run_appears_after_2_polls_and_succeeds_exit_0(self):
        """A run appears after 2 polls, then completes with success: exit 0 and first line correct."""
        list_calls = [0]
        run_data = {
            "databaseId": 1001,
            "headSha": "724ef84d8316a02c87263139978369ce1f766f3b",
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "completed",
            "conclusion": "success",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/1001",
        }

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "list" in cmd:
                list_calls[0] += 1
                if list_calls[0] == 1:
                    return 0, json.dumps([]), ""
                return 0, json.dumps([run_data]), ""
            if "run" in cmd and "view" in cmd:
                return 0, json.dumps(run_data), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return ["=== CI Digest: Unity CI #1001 ===", "Verdict: [SUCCESS]"], "SUCCESS"

        out = io.StringIO()
        clock = [100.0]

        def fake_mono():
            clock[0] += 10.0
            return clock[0]

        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="724ef84",
                appear_timeout=180,
                interval=15,
                monotonic_fn=fake_mono,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 0)
        self.assertEqual(list_calls[0], 2)
        output = out.getvalue()
        first_line = output.splitlines()[0]
        expected_first_line = (
            "ci wait: run 1001 success (724ef84, Unity CI) "
            "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/1001"
        )
        self.assertEqual(first_line, expected_first_line)
        self.assertIn("=== CI Digest: Unity CI #1001 ===", output)

    def test_run_failure_exits_1_with_failing_digest_lines(self):
        """A failure: exit 1, with the digest's failing-test lines present."""
        run_data = {
            "databaseId": 1002,
            "headSha": "abcdef123456",
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "completed",
            "conclusion": "failure",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/1002",
        }

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "list" in cmd:
                return 0, json.dumps([run_data]), ""
            if "run" in cmd and "view" in cmd:
                return 0, json.dumps(run_data), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return [
                "=== CI Digest: Unity CI #1002 ===",
                "- [FAILURE] Unity PlayMode",
                "    First failures (1):",
                "    * `SimulationTests.Tick_ThrowsException`",
            ], "FAILURE"

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="abcdef1",
                appear_timeout=180,
                interval=15,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 1)
        output = out.getvalue()
        self.assertIn("ci wait: run 1002 failure (abcdef1, Unity CI)", output)
        self.assertIn("* `SimulationTests.Tick_ThrowsException`", output)

    def test_no_run_appears_exits_5(self):
        """No run appears within appear-timeout: prints clear message and exits 5."""
        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "list" in cmd:
                return 0, json.dumps([]), ""
            return 0, "", ""

        clock = [100.0]

        def fake_mono():
            return clock[0]

        def fake_sleep(sec):
            clock[0] += sec

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="nonexistent123",
                appear_timeout=180,
                interval=15,
                monotonic_fn=fake_mono,
                sleep_fn=fake_sleep,
            )

        self.assertEqual(code, 5)
        self.assertEqual(clock[0] - 100.0, 180.0)
        self.assertEqual(out.getvalue().strip(), "ci wait: no run found for nonexistent123 after 180 s.")

    def test_max_wait_reached_exits_6_capped_sleep(self):
        """Max-wait reached: exit 6, with no overshoot beyond one capped sleep."""
        run_in_progress = {
            "databaseId": 1003,
            "headSha": "987654321",
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "in_progress",
            "conclusion": "",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/1003",
        }

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "list" in cmd:
                return 0, json.dumps([run_in_progress]), ""
            if "run" in cmd and "view" in cmd:
                return 0, json.dumps(run_in_progress), ""
            return 0, "", ""

        clock = [1000.0]
        sleeps = []

        def fake_mono():
            return clock[0]

        def fake_sleep(sec):
            sleeps.append(sec)
            clock[0] += sec

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="9876543",
                interval=60,
                max_wait=75,  # 75s: first sleep 60s, second sleep capped at 15s!
                monotonic_fn=fake_mono,
                sleep_fn=fake_sleep,
            )

        self.assertEqual(code, 6)
        # Verify sleep was capped to remaining time exactly: 60s then 15s = 75s
        self.assertEqual(clock[0] - 1000.0, 75.0)
        self.assertEqual(sleeps, [60, 15.0])
        self.assertEqual(
            out.getvalue().strip(),
            "ci wait: run 1003 still in_progress after 75 s. Start ci wait again.",
        )

    def test_gh_errors_then_success_quiet_and_10min_warning_appears_once(self):
        """gh errors for a while, then success: no output until done; the 10-minute warning appears once."""
        run_initial = {
            "databaseId": 1004,
            "headSha": "111222333",
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "in_progress",
            "conclusion": "",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/1004",
        }
        run_completed = dict(run_initial, status="completed", conclusion="success")

        clock = [0.0]
        call_count = [0]

        def fake_mono():
            return clock[0]

        def fake_sleep(sec):
            clock[0] += sec

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "list" in cmd:
                return 0, json.dumps([run_initial]), ""
            if "run" in cmd and "view" in cmd:
                call_count[0] += 1
                # Fail for first 800 seconds (past 10 min mark = 600s)
                if clock[0] < 800.0:
                    return 1, "", "connection reset by peer"
                # Then succeed with completed run
                return 0, json.dumps(run_completed), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return ["=== CI Digest ==="], "SUCCESS"

        out = io.StringIO()
        err = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out), \
             patch("sys.stderr", err):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="1112223",
                interval=60,
                max_wait=1200,
                monotonic_fn=fake_mono,
                sleep_fn=fake_sleep,
            )

        self.assertEqual(code, 0)
        err_output = err.getvalue()
        self.assertIn("ci wait: warning: persistent failure connecting to GitHub for", err_output)
        self.assertIn("minutes (connection reset by peer). Continuing to wait...", err_output)
        self.assertEqual(err_output.count("ci wait: warning:"), 1)
        self.assertIn("ci wait: run 1004 success (1112223, Unity CI)", out.getvalue())

    def test_two_runs_for_one_sha_both_reported(self):
        """When two runs match a SHA and no workflow is given, both runs are reported."""
        run1 = {
            "databaseId": 2001,
            "headSha": "sharedsha123",
            "name": "Compile Gate",
            "workflowName": "Compile Gate",
            "status": "completed",
            "conclusion": "success",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/2001",
        }
        run2 = {
            "databaseId": 2002,
            "headSha": "sharedsha123",
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "completed",
            "conclusion": "success",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/2002",
        }

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "list" in cmd:
                return 0, json.dumps([run1, run2]), ""
            if "run" in cmd and "view" in cmd:
                rid = int(cmd[cmd.index("view") + 1])
                return 0, json.dumps(run1 if rid == 2001 else run2), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return [f"=== CI Digest for #{run_id} ==="], "SUCCESS"

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="sharedsha",
                interval=15,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 0)
        output = out.getvalue()
        self.assertIn("ci wait: run 2001 success (shareds, Compile Gate)", output)
        self.assertIn("=== CI Digest for #2001 ===", output)
        self.assertIn("ci wait: run 2002 success (shareds, Unity CI)", output)
        self.assertIn("=== CI Digest for #2002 ===", output)

    def test_nothing_printed_while_waiting(self):
        """Nothing is printed to stdout or stderr during polling while runs are in progress."""
        poll_step = [0]
        run_data = {
            "databaseId": 3001,
            "headSha": "quietsha123",
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "in_progress",
            "conclusion": "",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/3001",
        }

        captured_during_wait = []

        out = io.StringIO()
        err = io.StringIO()

        def fake_sleep(sec):
            # Check what's in stdout and stderr during sleep
            captured_during_wait.append((out.getvalue(), err.getvalue()))

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "list" in cmd:
                return 0, json.dumps([run_data]), ""
            if "run" in cmd and "view" in cmd:
                poll_step[0] += 1
                if poll_step[0] < 3:
                    return 0, json.dumps(run_data), ""
                completed = dict(run_data, status="completed", conclusion="success")
                return 0, json.dumps(completed), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return ["=== CI Digest ==="], "SUCCESS"

        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out), \
             patch("sys.stderr", err):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="quietsha",
                interval=15,
                sleep_fn=fake_sleep,
            )

        self.assertEqual(code, 0)
        # All sleep snapshots must have empty stdout and stderr
        self.assertTrue(len(captured_during_wait) >= 2)
        for snap_out, snap_err in captured_during_wait:
            self.assertEqual(snap_out, "")
            self.assertEqual(snap_err, "")

        # Only after completion is output printed
        self.assertIn("ci wait: run 3001 success", out.getvalue())

    def test_short_sha_resolves_via_git_and_finds_run(self):
        """Short SHA resolves to full SHA via git rev-parse inside repository and succeeds."""
        full_40 = "724ef84d8316a02c87263139978369ce1f766f3b"
        run_data = {
            "databaseId": 4001,
            "headSha": full_40,
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "completed",
            "conclusion": "success",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/4001",
        }

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "rev-parse" in cmd and "--is-inside-work-tree" in cmd:
                return 0, "true", ""
            if "config" in cmd and "remote.origin.url" in cmd:
                return 0, f"https://github.com/{self.repo}.git", ""
            if "rev-parse" in cmd and f"724ef84^{{commit}}" in cmd:
                return 0, full_40, ""
            if "run" in cmd and "list" in cmd and full_40 in cmd:
                return 0, json.dumps([run_data]), ""
            if "run" in cmd and "view" in cmd:
                return 0, json.dumps(run_data), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return ["=== CI Digest ==="], "SUCCESS"

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="724ef84",
                interval=15,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 0)
        self.assertIn("ci wait: run 4001 success (724ef84, Unity CI)", out.getvalue())

    def test_short_sha_resolves_via_gh_run_list_limit_50(self):
        """Short SHA when outside git repository resolves via gh run list --limit 50 prefix matching."""
        full_40 = "abcdef1234567890abcdef1234567890abcdef12"
        run_data = {
            "databaseId": 4002,
            "headSha": full_40,
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "completed",
            "conclusion": "success",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/4002",
        }

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "git" in cmd:
                return 1, "", "not a git repo"
            if "run" in cmd and "list" in cmd:
                return 0, json.dumps([run_data]), ""
            if "run" in cmd and "view" in cmd:
                return 0, json.dumps(run_data), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return ["=== CI Digest ==="], "SUCCESS"

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="abcdef1",
                interval=15,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 0)
        self.assertIn("ci wait: run 4002 success (abcdef1, Unity CI)", out.getvalue())

    def test_ambiguous_prefix_after_appear_timeout_exits_5_naming_prefix(self):
        """Ambiguous prefix matching multiple SHAs in recent runs exits 5 after appear timeout naming prefix."""
        run1 = {"databaseId": 4011, "headSha": "abcdef1111111111111111111111111111111111"}
        run2 = {"databaseId": 4012, "headSha": "abcdef1222222222222222222222222222222222"}

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "git" in cmd:
                return 1, "", ""
            if "run" in cmd and "list" in cmd:
                return 0, json.dumps([run1, run2]), ""
            return 0, "", ""

        clock = [0.0]

        def fake_mono():
            return clock[0]

        def fake_sleep(sec):
            clock[0] += sec

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="abcdef1",
                appear_timeout=60,
                interval=15,
                monotonic_fn=fake_mono,
                sleep_fn=fake_sleep,
            )

        self.assertEqual(code, 5)
        out_str = out.getvalue()
        self.assertIn("abcdef1", out_str)
        self.assertIn("ambiguous SHA prefix 'abcdef1'", out_str)

    def test_unknown_prefix_after_appear_timeout_exits_5_naming_prefix(self):
        """Unknown prefix not found in recent runs exits 5 after appear timeout naming prefix."""
        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "git" in cmd:
                return 1, "", ""
            if "run" in cmd and "list" in cmd:
                return 0, json.dumps([]), ""
            return 0, "", ""

        clock = [0.0]

        def fake_mono():
            return clock[0]

        def fake_sleep(sec):
            clock[0] += sec

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="unk9999",
                appear_timeout=60,
                interval=15,
                monotonic_fn=fake_mono,
                sleep_fn=fake_sleep,
            )

        self.assertEqual(code, 5)
        out_str = out.getvalue()
        self.assertIn("unk9999", out_str)
        self.assertIn("no run found for unk9999", out_str)

    def test_prefix_under_7_characters_gives_exit_2(self):
        """A SHA prefix shorter than 7 characters exits with code 2."""
        err = io.StringIO()
        with patch("sys.stderr", err):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="123456",
            )
        self.assertEqual(code, 2)
        self.assertIn("Commit SHA prefix must be at least 7 characters", err.getvalue())

    def test_branch_ignores_stale_completed_run_and_waits_for_new(self):
        """With --branch, old runs created >60s before invocation are ignored, waiting for new run."""
        # 2026-11-09T00:00:00Z = 1794182400.0
        # 2026-11-09T00:03:00Z = 1794182580.0
        # Start wall clock: 1794182570.0 (old run created 170s earlier -> >60s stale)
        stale_run = {
            "databaseId": 5001,
            "headSha": "old1111111",
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "completed",
            "conclusion": "success",
            "createdAt": "2026-11-09T00:00:00Z",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/5001",
        }
        new_run = {
            "databaseId": 5002,
            "headSha": "new2222222",
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "completed",
            "conclusion": "success",
            "createdAt": "2026-11-09T00:03:00Z",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/5002",
        }

        call_step = [0]

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "list" in cmd:
                call_step[0] += 1
                if call_step[0] == 1:
                    # First poll only has stale run
                    return 0, json.dumps([stale_run]), ""
                # Second poll has both new run and stale run
                return 0, json.dumps([new_run, stale_run]), ""
            if "run" in cmd and "view" in cmd:
                return 0, json.dumps(new_run), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return [f"=== CI Digest for #{run_id} ==="], "SUCCESS"

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                branch="g02-feature",
                include_existing=False,
                interval=15,
                wall_clock_fn=lambda: 1794182570.0,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 0)
        output = out.getvalue()
        self.assertIn("ci wait: run 5002 success", output)
        self.assertNotIn("5001", output)

    def test_branch_with_include_existing_returns_old_run(self):
        """With --branch and --include-existing, an old run is accepted immediately."""
        stale_run = {
            "databaseId": 5001,
            "headSha": "old1111111",
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "completed",
            "conclusion": "success",
            "createdAt": "2026-11-09T00:00:00Z",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/5001",
        }

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "list" in cmd:
                return 0, json.dumps([stale_run]), ""
            if "run" in cmd and "view" in cmd:
                return 0, json.dumps(stale_run), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return ["=== CI Digest for #5001 ==="], "SUCCESS"

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                branch="g02-feature",
                include_existing=True,
                interval=15,
                wall_clock_fn=lambda: 1794182570.0,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 0)
        self.assertIn("ci wait: run 5001 success", out.getvalue())

    def test_late_runs_for_sha_second_run_appears_on_poll_3(self):
        """When waiting for a SHA, late-appearing runs on poll 3 are discovered and waited for."""
        full_sha = "latersha1234567890abcdef1234567890abcdef"
        run1_in_progress = {
            "databaseId": 6001,
            "headSha": full_sha,
            "workflowName": "Compile Gate",
            "name": "Compile Gate",
            "status": "in_progress",
            "conclusion": "",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/6001",
        }
        run1_done = dict(run1_in_progress, status="completed", conclusion="success")
        run2_in_progress = {
            "databaseId": 6002,
            "headSha": full_sha,
            "workflowName": "Unity EditMode",
            "name": "Unity EditMode",
            "status": "in_progress",
            "conclusion": "",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/6002",
        }
        run2_done = dict(run2_in_progress, status="completed", conclusion="success")

        relist_step = [0]
        run2_completed = [False]

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "list" in cmd:
                relist_step[0] += 1
                if relist_step[0] < 3:
                    # Polls 1 and 2 only know about run1
                    return 0, json.dumps([run1_in_progress]), ""
                # Poll 3 introduces run2
                return 0, json.dumps([run1_done, run2_in_progress if not run2_completed[0] else run2_done]), ""
            if "run" in cmd and "view" in cmd:
                if "6001" in cmd:
                    if relist_step[0] < 3:
                        return 0, json.dumps(run1_in_progress), ""
                    return 0, json.dumps(run1_done), ""
                if "6002" in cmd:
                    # Run 2 becomes completed after being polled
                    run2_completed[0] = True
                    return 0, json.dumps(run2_done), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return [f"=== CI Digest for #{run_id} ==="], "SUCCESS"

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha=full_sha,
                workflow=None,
                interval=15,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 0)
        output = out.getvalue()
        self.assertIn("ci wait: run 6001 success", output)
        self.assertIn("ci wait: run 6002 success", output)

    def test_run_id_not_found_gives_exit_5(self):
        """A --run-id reported as not found by gh returns exit 5 with 'run <id> not found'."""
        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "view" in cmd:
                return 1, "", "failed to get run: HTTP 404: Not Found (https://api.github.com/...)"
            return 0, "", ""

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                run_id="888888",
            )

        self.assertEqual(code, 5)
        self.assertIn("ci wait: run 888888 not found", out.getvalue())

    def test_appear_phase_transient_error_with_10min_warning_then_success(self):
        """Transient gh errors during appear phase retry with backoff, emit 10-minute warning, then recover."""
        run_data = {
            "databaseId": 888889,
            "headSha": "724ef84",
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "completed",
            "conclusion": "success",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/888889",
        }

        clock = [0.0]

        def fake_mono():
            return clock[0]

        def fake_sleep(sec):
            clock[0] += sec

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "view" in cmd:
                if clock[0] < 800.0:
                    return 1, "", "connection reset by peer"
                return 0, json.dumps(run_data), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return ["=== CI Digest ==="], "SUCCESS"

        out = io.StringIO()
        err = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out), \
             patch("sys.stderr", err):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                run_id="888889",
                appear_timeout=180,
                interval=60,
                monotonic_fn=fake_mono,
                sleep_fn=fake_sleep,
            )

        self.assertEqual(code, 0)
        self.assertIn("ci wait: warning: persistent failure connecting to GitHub for", err.getvalue())
        self.assertIn("ci wait: run 888889 success", out.getvalue())

    def test_exit_6_poll_once_more_after_final_sleep_reports_real_result(self):
        """After the final capped sleep, poll once more before returning exit 6; run completed during sleep exits 0."""
        clock = [0.0]

        def fake_mono():
            return clock[0]

        def fake_sleep(sec):
            clock[0] += sec

        run_in_progress = {
            "databaseId": 999991,
            "headSha": "pollonce123",
            "name": "Unity CI",
            "workflowName": "Unity CI",
            "status": "in_progress",
            "conclusion": "",
            "url": "https://github.com/tosumitdhaka/trishul-tactical-engine/actions/runs/999991",
        }
        run_done = dict(run_in_progress, status="completed", conclusion="success")

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "run" in cmd and "view" in cmd:
                # Until 120s, it's in_progress. On the final poll at t = 120s, it's completed!
                if clock[0] < 120.0:
                    return 0, json.dumps(run_in_progress), ""
                return 0, json.dumps(run_done), ""
            return 0, "", ""

        def mock_digest(repo, run_id, max_failures=10):
            return ["=== CI Digest: Unity CI #999991 ==="], "SUCCESS"

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("gh_helper.generate_ci_digest", side_effect=mock_digest), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                run_id="999991",
                interval=60,
                max_wait=120,
                monotonic_fn=fake_mono,
                sleep_fn=fake_sleep,
            )

        self.assertEqual(code, 0)
        self.assertIn("ci wait: run 999991 success", out.getvalue())
        self.assertNotIn("still in_progress after", out.getvalue())


    def test_appear_phase_max_wait_exhausted_exits_6_without_busy_loop(self):
        """When --max-wait runs out during the appear phase, exit 6 immediately with bounded gh calls."""
        gh_calls = [0]

        def mock_run_cmd(cmd, input_text=None, cwd=None):
            if "git" in cmd:
                return 1, "", ""
            if "run" in cmd and "list" in cmd:
                gh_calls[0] += 1
                return 0, json.dumps([]), ""  # run never appears
            return 0, "", ""

        clock = [0.0]

        def fake_mono():
            return clock[0]

        def fake_sleep(sec):
            # Enforce minimum sleep of 1s (what the fix guarantees)
            self.assertGreaterEqual(sec, 1, f"sleep was called with {sec}s — must be >= 1s to avoid busy loop")
            clock[0] += sec

        out = io.StringIO()
        with patch("gh_helper.run_cmd", side_effect=mock_run_cmd), \
             patch("sys.stdout", out):
            code = gh_helper.wait_for_ci_runs(
                repo=self.repo,
                sha="abcdef1",
                appear_timeout=180,
                interval=15,
                max_wait=60,
                monotonic_fn=fake_mono,
                sleep_fn=fake_sleep,
            )

        # Should exit 6 when max-wait runs out, not spin until appear-timeout
        self.assertEqual(code, 6)
        # Clock should be ~60s, not 180s (not spin until appear-timeout)
        self.assertLessEqual(clock[0], 100, f"clock overshot ({clock[0]}s): should exit at ~60s not spin until appear-timeout")
        # gh calls should be bounded: at ~15s interval over 60s = at most ~5 calls, not hundreds
        self.assertLessEqual(gh_calls[0], 10, f"too many gh calls ({gh_calls[0]}): indicates busy loop")
        # Message must name the scenario
        self.assertIn("Start ci wait again", out.getvalue())


if __name__ == "__main__":
    unittest.main()

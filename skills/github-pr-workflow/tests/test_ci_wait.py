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


if __name__ == "__main__":
    unittest.main()

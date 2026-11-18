#!/usr/bin/env python3
"""Unit tests for hub_wake_hook.py: automatic wake hook for Claude desktop chats."""

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import hub_messenger  # noqa: E402
import hub_wake_hook  # noqa: E402


class TestHubWakeHook(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.token_file = self.base_dir / "test.token"
        self.secret_token = "SECRET_TOKEN_HOOK_998877"
        self.token_file.write_text(self.secret_token, encoding="utf-8")

        self.sessions_file = self.base_dir / "claude_sessions.json"
        self.test_session_id = "test-session-uuid-12345678"
        self.participant = "manager"
        self.project = "trishul-tactical-engine"

        # Initial mapping
        initial_sessions = {
            self.test_session_id: {
                "participant": self.participant,
                "project": self.project,
                "token_file": str(self.token_file),
            }
        }
        self.sessions_file.write_text(json.dumps(initial_sessions, indent=2), encoding="utf-8")

    def tearDown(self):
        import logging
        logging.shutdown()
        self.temp_dir.cleanup()

    def test_unmapped_session_exits_0_silent(self):
        """An unmapped session exits 0 silently with no stdout or stderr."""
        stdin_json = json.dumps({"session_id": "unmapped-session-9999", "hook_event_name": "Stop"})
        out = io.StringIO()
        err = io.StringIO()

        with patch("sys.stdout", out), patch("sys.stderr", err):
            code = hub_wake_hook.run_hook_mode(
                raw_stdin=stdin_json,
                base_dir=self.base_dir,
            )

        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")

    def test_invalid_stdin_exits_0(self):
        """Invalid stdin (empty, non-JSON, non-dict, missing session_id) exits 0 silently."""
        for invalid_input in ["", "   ", "not-a-json", "[]", "123", json.dumps({"hook_event_name": "Stop"})]:
            out = io.StringIO()
            err = io.StringIO()
            with patch("sys.stdout", out), patch("sys.stderr", err):
                code = hub_wake_hook.run_hook_mode(
                    raw_stdin=invalid_input,
                    base_dir=self.base_dir,
                )
            self.assertEqual(code, 0, f"Failed for invalid input: {invalid_input!r}")
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(err.getvalue(), "")

    def test_mail_arrives_exits_2_stderr_wake_line_stdout_silent(self):
        """Mail arrives: exits 2 with hub_wait notification line on stderr and nothing on stdout."""
        def mock_query(hub_url, project, token, timeout=15):
            return [{"name": self.participant, "pending": 2}], project, None

        stdin_json = json.dumps({"session_id": self.test_session_id, "hook_event_name": "Stop"})
        out = io.StringIO()
        err = io.StringIO()

        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out), patch("sys.stderr", err):
            code = hub_wake_hook.run_hook_mode(
                raw_stdin=stdin_json,
                base_dir=self.base_dir,
                interval=5,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        expected_wake_line = (
            f"hub_wait: {self.participant} has 2 pending message(s). "
            "Read your hub inbox, then start hub_wait again.\n"
        )
        self.assertEqual(err.getvalue(), expected_wake_line)

        # Check log file
        log_file = self.base_dir / "hub_wake_hook.log"
        self.assertTrue(log_file.exists())
        log_content = log_file.read_text(encoding="utf-8")
        self.assertIn(f"START event=Stop participant={self.participant}", log_content)
        self.assertIn(f"EXIT event=Stop participant={self.participant} exit=2 reason=mail_arrived pending=2", log_content)

    def test_lock_held_exits_0_silent(self):
        """Lock already held by another waiter exits 0 silently."""
        lock_file = self.base_dir / f"hub_wait.{self.participant}.lock"
        existing_lock = hub_messenger.OSLock(lock_file)
        self.assertTrue(existing_lock.try_acquire())
        existing_lock.write_diagnostics({"pid": 9876, "participant": self.participant})

        try:
            stdin_json = json.dumps({"session_id": self.test_session_id, "hook_event_name": "Stop"})
            out = io.StringIO()
            err = io.StringIO()

            with patch("sys.stdout", out), patch("sys.stderr", err):
                code = hub_wake_hook.run_hook_mode(
                    raw_stdin=stdin_json,
                    base_dir=self.base_dir,
                )

            self.assertEqual(code, 0)
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(err.getvalue(), "")

            log_file = self.base_dir / "hub_wake_hook.log"
            self.assertTrue(log_file.exists())
            log_content = log_file.read_text(encoding="utf-8")
            self.assertIn("reason=lock_already_held", log_content)
        finally:
            existing_lock.release()

    def test_participant_missing_exits_0_with_log_line_only(self):
        """Participant missing from hub: exits 0 with a log line only, nothing on stdout/stderr."""
        def mock_query(hub_url, project, token, timeout=15):
            return [{"name": "other-agent", "pending": 5}], project, None

        stdin_json = json.dumps({"session_id": self.test_session_id, "hook_event_name": "Stop"})
        out = io.StringIO()
        err = io.StringIO()

        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out), patch("sys.stderr", err):
            code = hub_wake_hook.run_hook_mode(
                raw_stdin=stdin_json,
                base_dir=self.base_dir,
                interval=5,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")

        log_file = self.base_dir / "hub_wake_hook.log"
        self.assertTrue(log_file.exists())
        log_content = log_file.read_text(encoding="utf-8")
        self.assertIn(f"participant '{self.participant}' not found in project '{self.project}'", log_content)
        self.assertIn("reason=participant_not_found", log_content)

    def test_max_wait_reached_exits_2_with_rearm_line(self):
        """Max-wait reached: exits 2 with re-arm message on stderr."""
        clock = [1000.0]

        def fake_mono():
            val = clock[0]
            clock[0] += 82800.0  # 23 hours
            return val

        def mock_query(hub_url, project, token, timeout=15):
            return [{"name": self.participant, "pending": 0}], project, None

        stdin_json = json.dumps({"session_id": self.test_session_id, "hook_event_name": "Stop"})
        out = io.StringIO()
        err = io.StringIO()

        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out), patch("sys.stderr", err):
            code = hub_wake_hook.run_hook_mode(
                raw_stdin=stdin_json,
                base_dir=self.base_dir,
                interval=30,
                max_wait=82800,
                monotonic_fn=fake_mono,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        expected_line = f"hub_wake_hook: no mail for {self.participant} after 23 h; re-armed at end of this turn.\n"
        self.assertEqual(err.getvalue(), expected_line)

        log_file = self.base_dir / "hub_wake_hook.log"
        self.assertTrue(log_file.exists())
        log_content = log_file.read_text(encoding="utf-8")
        self.assertIn("reason=max_wait", log_content)

    # -------------------------------------------------------------------------
    # Anti-Loop Tests
    # -------------------------------------------------------------------------

    def test_anti_loop_case_1_one_wake_for_unchanged_pending_mail(self):
        """Case 1: First hook run wakes for pending=2. Second hook run with unchanged pending=2 does NOT wake."""
        def mock_query(hub_url, project, token, timeout=15):
            return [{"name": self.participant, "pending": 2}], project, None

        stdin_json = json.dumps({"session_id": self.test_session_id, "hook_event_name": "Stop"})
        wall_clock = [1000.0]
        mono_clock = [0.0]

        # First turn: pending = 2 -> wakes with exit 2
        out1 = io.StringIO()
        err1 = io.StringIO()
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out1), patch("sys.stderr", err1):
            code1 = hub_wake_hook.run_hook_mode(
                raw_stdin=stdin_json,
                base_dir=self.base_dir,
                interval=5,
                time_fn=lambda: wall_clock[0],
                monotonic_fn=lambda: mono_clock[0],
                sleep_fn=lambda _: None,
            )
        self.assertEqual(code1, 2)
        self.assertIn("has 2 pending message(s)", err1.getvalue())

        # Verify state file was updated
        state_file = self.base_dir / f"hub_wake_hook.{self.participant}.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["last_woken_pending"], 2)
        self.assertEqual(state["last_woken_at"], 1000.0)

        # Second turn: chat ends turn without reading mail, 10s later (wall_clock = 1010.0).
        # Pending is still 2. It must NOT wake. We give max_wait=20 so it eventually times out.
        wall_clock[0] = 1010.0
        mono_clock[0] = 0.0

        def advance_mono():
            val = mono_clock[0]
            mono_clock[0] += 25.0  # triggers max_wait on poll 2
            return val

        out2 = io.StringIO()
        err2 = io.StringIO()
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out2), patch("sys.stderr", err2):
            code2 = hub_wake_hook.run_hook_mode(
                raw_stdin=stdin_json,
                base_dir=self.base_dir,
                interval=5,
                max_wait=20,
                time_fn=lambda: wall_clock[0],
                monotonic_fn=advance_mono,
                sleep_fn=lambda _: None,
            )
        # Should exit 2 due to max_wait, NOT due to pending mail!
        self.assertEqual(code2, 2)
        self.assertNotIn("has 2 pending message(s)", err2.getvalue())
        self.assertIn("re-armed at end of this turn", err2.getvalue())

    def test_anti_loop_case_2_new_wake_when_pending_rises(self):
        """Case 2: If mail pending count rises (e.g. from 2 to 3), wake triggers again immediately."""
        state_file = self.base_dir / f"hub_wake_hook.{self.participant}.json"
        hub_wake_hook.save_anti_loop_state(state_file, pending=2, woken_at=1000.0)

        # Hub now returns pending = 3
        def mock_query(hub_url, project, token, timeout=15):
            return [{"name": self.participant, "pending": 3}], project, None

        stdin_json = json.dumps({"session_id": self.test_session_id, "hook_event_name": "Stop"})
        out = io.StringIO()
        err = io.StringIO()

        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out), patch("sys.stderr", err):
            code = hub_wake_hook.run_hook_mode(
                raw_stdin=stdin_json,
                base_dir=self.base_dir,
                interval=5,
                time_fn=lambda: 1010.0,  # only 10s after last wake
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 2)
        self.assertIn("has 3 pending message(s)", err.getvalue())
        # State file must be updated to 3
        state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["last_woken_pending"], 3)
        self.assertEqual(state["last_woken_at"], 1010.0)

    def test_anti_loop_case_3_reminder_after_15_minutes_on_fake_clock(self):
        """Case 3: If pending mail stays unchanged, wake triggers after 15 minutes (900 s) reminder interval."""
        state_file = self.base_dir / f"hub_wake_hook.{self.participant}.json"
        hub_wake_hook.save_anti_loop_state(state_file, pending=3, woken_at=1000.0)

        # Hub still returns pending = 3
        def mock_query(hub_url, project, token, timeout=15):
            return [{"name": self.participant, "pending": 3}], project, None

        stdin_json = json.dumps({"session_id": self.test_session_id, "hook_event_name": "Stop"})
        out = io.StringIO()
        err = io.StringIO()

        # Advance fake clock by 905 seconds (1000 + 905 = 1905 >= 900)
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out), patch("sys.stderr", err):
            code = hub_wake_hook.run_hook_mode(
                raw_stdin=stdin_json,
                base_dir=self.base_dir,
                interval=5,
                remind_after=900.0,
                time_fn=lambda: 1905.0,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 2)
        self.assertIn("has 3 pending message(s)", err.getvalue())
        state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["last_woken_at"], 1905.0)

    def test_anti_loop_case_4_reset_at_0(self):
        """Case 4: When pending reaches 0, state is reset; subsequent mail wakes immediately."""
        state_file = self.base_dir / f"hub_wake_hook.{self.participant}.json"
        hub_wake_hook.save_anti_loop_state(state_file, pending=3, woken_at=1000.0)

        # Poll 1: pending = 0 (mail read!)
        # Poll 2: pending = 1 (new mail arrives)
        polls = [0]

        def mock_query(hub_url, project, token, timeout=15):
            polls[0] += 1
            if polls[0] == 1:
                return [{"name": self.participant, "pending": 0}], project, None
            return [{"name": self.participant, "pending": 1}], project, None

        stdin_json = json.dumps({"session_id": self.test_session_id, "hook_event_name": "Stop"})
        out = io.StringIO()
        err = io.StringIO()

        # Clock is at 1010.0 (only 10 seconds since last wake, well below 900s)
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out), patch("sys.stderr", err):
            code = hub_wake_hook.run_hook_mode(
                raw_stdin=stdin_json,
                base_dir=self.base_dir,
                interval=5,
                time_fn=lambda: 1010.0,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 2)
        self.assertIn("has 1 pending message(s)", err.getvalue())
        state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["last_woken_pending"], 1)
        self.assertEqual(state["last_woken_at"], 1010.0)

    # -------------------------------------------------------------------------
    # register, unregister, and list subcommand tests
    # -------------------------------------------------------------------------

    def test_register_from_env_variable(self):
        """register uses CLAUDE_CODE_SESSION_ID when --session-id is not provided."""
        env_session = "env-session-uuid-88889999"
        out = io.StringIO()
        with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": env_session}), patch("sys.stdout", out):
            code = hub_wake_hook.main([
                "--base-dir", str(self.base_dir),
                "register",
                "--participant", "architect",
                "--project", "trishul-tactical-engine",
            ])

        self.assertEqual(code, 0)
        self.assertIn("Registered architect", out.getvalue())
        self.assertIn(env_session[:8], out.getvalue())

        sessions = json.loads(self.sessions_file.read_text(encoding="utf-8"))
        self.assertIn(env_session, sessions)
        self.assertEqual(sessions[env_session]["participant"], "architect")

    def test_register_session_id_flag_overrides_env(self):
        """register flag --session-id takes precedence over CLAUDE_CODE_SESSION_ID."""
        env_session = "env-session-1111"
        cli_session = "cli-session-2222-3333-4444"
        out = io.StringIO()
        with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": env_session}), patch("sys.stdout", out):
            code = hub_wake_hook.main([
                "--base-dir", str(self.base_dir),
                "register",
                "--participant", "orchestrator-claude",
                "--session-id", cli_session,
            ])

        self.assertEqual(code, 0)
        self.assertIn(cli_session[:8], out.getvalue())

        sessions = json.loads(self.sessions_file.read_text(encoding="utf-8"))
        self.assertIn(cli_session, sessions)
        self.assertNotIn(env_session, sessions)

    def test_register_missing_session_id_exits_2(self):
        """register without --session-id and without CLAUDE_CODE_SESSION_ID exits 2."""
        err = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch("sys.stderr", err):
            # Ensure CLAUDE_CODE_SESSION_ID is not present
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            code = hub_wake_hook.main([
                "--base-dir", str(self.base_dir),
                "register",
                "--participant", "manager",
            ])

        self.assertEqual(code, 2)
        self.assertIn("CLAUDE_CODE_SESSION_ID environment variable not set", err.getvalue())

    def test_register_replaces_old_entry_for_same_participant_and_project(self):
        """register replaces any prior session for the same participant and project."""
        old_session = self.test_session_id  # Already registered for 'manager' in setUp
        new_session = "new-replacement-session-9999"

        sessions_before = json.loads(self.sessions_file.read_text(encoding="utf-8"))
        self.assertIn(old_session, sessions_before)

        out = io.StringIO()
        with patch("sys.stdout", out):
            code = hub_wake_hook.main([
                "--base-dir", str(self.base_dir),
                "register",
                "--participant", "manager",
                "--project", "trishul-tactical-engine",
                "--session-id", new_session,
            ])

        self.assertEqual(code, 0)
        self.assertIn(new_session[:8], out.getvalue())

        sessions_after = json.loads(self.sessions_file.read_text(encoding="utf-8"))
        self.assertNotIn(old_session, sessions_after)
        self.assertIn(new_session, sessions_after)
        self.assertEqual(sessions_after[new_session]["participant"], "manager")

    def test_unregister_and_list(self):
        """unregister removes session and list displays table of registered sessions."""
        # Check initial list
        out_list1 = io.StringIO()
        with patch("sys.stdout", out_list1):
            code_list1 = hub_wake_hook.main(["--base-dir", str(self.base_dir), "list"])
        self.assertEqual(code_list1, 0)
        self.assertIn(self.test_session_id, out_list1.getvalue())
        self.assertIn(self.participant, out_list1.getvalue())

        # Unregister by session ID
        out_unreg = io.StringIO()
        with patch("sys.stdout", out_unreg):
            code_unreg = hub_wake_hook.main([
                "--base-dir", str(self.base_dir),
                "unregister",
                "--session-id", self.test_session_id,
            ])
        self.assertEqual(code_unreg, 0)
        self.assertIn(self.test_session_id[:8], out_unreg.getvalue())

        # List should now report empty
        out_list2 = io.StringIO()
        with patch("sys.stdout", out_list2):
            code_list2 = hub_wake_hook.main(["--base-dir", str(self.base_dir), "list"])
        self.assertEqual(code_list2, 0)
        self.assertIn("No registered Claude sessions.", out_list2.getvalue())

    def test_token_string_never_appears_in_output_log_or_state(self):
        """Bearer token string must never appear in stdout, stderr, log, or state files."""
        # Cause HTTP 401 error
        def mock_query(hub_url, project, token, timeout=15):
            return None, project, urllib.error.HTTPError(
                url="http://127.0.0.1:8765/participants",
                code=401,
                msg="Unauthorized",
                hdrs=None,
                fp=None,
            )

        stdin_json = json.dumps({"session_id": self.test_session_id, "hook_event_name": "Stop"})
        out = io.StringIO()
        err = io.StringIO()
        mono_clock = [0.0]

        def fake_mono():
            val = mono_clock[0]
            mono_clock[0] += 15.0
            return val

        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out), patch("sys.stderr", err):
            hub_wake_hook.run_hook_mode(
                raw_stdin=stdin_json,
                base_dir=self.base_dir,
                interval=5,
                max_wait=10,
                monotonic_fn=fake_mono,
                sleep_fn=lambda _: None,
            )

        self.assertNotIn(self.secret_token, out.getvalue())
        self.assertNotIn(self.secret_token, err.getvalue())

        # Search all files under base_dir except the secret source token_file
        for p in self.base_dir.rglob("*"):
            if p.is_file() and p != self.token_file:
                content = p.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn(
                    self.secret_token,
                    content,
                    f"Secret token leaked into file: {p}",
                )


if __name__ == "__main__":
    unittest.main()

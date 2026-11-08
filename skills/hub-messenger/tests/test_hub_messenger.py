#!/usr/bin/env python3
"""Unit tests for hub_messenger.py: participant parsing, wake rules, state restart, and token secrecy."""

import io
import json
import logging
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import hub_messenger  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "participants_canned.json"


class TestHubMessenger(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.config_path = self.base_dir / "config.json"
        self.state_path = self.base_dir / "state.json"
        self.log_path = self.base_dir / "hub-messenger.log"
        self.token_path = self.base_dir / "fake.token"
        self.fake_secret = "SUPER_SECRET_BEARER_TOKEN_ABCD_9876543210"
        self.token_path.write_text(self.fake_secret, encoding="utf-8")

        # Clear logger handlers between tests
        logger = logging.getLogger("hub-messenger")
        for h in list(logger.handlers):
            h.close()
        logger.handlers.clear()

    def tearDown(self):
        logger = logging.getLogger("hub-messenger")
        for h in list(logger.handlers):
            h.close()
        logger.handlers.clear()
        self.temp_dir.cleanup()

    def test_canned_participant_json_fixture(self):
        self.assertTrue(FIXTURE_PATH.exists())
        participants = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(participants), 5)
        names = [p["name"] for p in participants]
        self.assertIn("architect", names)
        self.assertIn("manager", names)
        self.assertIn("orchestrator-codex", names)
        self.assertIn("orchestrator-claude", names)
        self.assertIn("phase-reviewer-codex", names)

    def test_manager_is_never_woken(self):
        p_manager = {
            "name": "manager",
            "role": "project-manager",
            "address": "trishul-tactical-engine/manager",
            "pending": 10,
            "waiting": False,
        }
        p_state = {"last_pending": 0, "last_wake_ts": 0.0}
        now_ts = 1000.0

        should_wake, reason = hub_messenger.should_wake_participant(p_manager, p_state, now_ts)
        self.assertFalse(should_wake)
        self.assertIn("Manager is never woken", reason)

    def test_waiting_participant_is_not_woken(self):
        p_waiting = {
            "name": "orchestrator-claude",
            "role": "orchestrator",
            "pending": 5,
            "waiting": True,  # Actively in inbox_wait
        }
        p_state = {"last_pending": 0, "last_wake_ts": 0.0}
        now_ts = 1000.0

        should_wake, reason = hub_messenger.should_wake_participant(p_waiting, p_state, now_ts)
        self.assertFalse(should_wake)
        self.assertIn("actively waiting", reason)

    def test_pending_rising_triggers_wake(self):
        p_worker = {
            "name": "orchestrator-codex",
            "role": "orchestrator",
            "pending": 3,
            "waiting": False,
        }
        # Last known pending was 1, woke 60 seconds ago
        p_state = {"last_pending": 1, "last_wake_ts": 940.0}
        now_ts = 1000.0

        should_wake, reason = hub_messenger.should_wake_participant(p_worker, p_state, now_ts)
        self.assertTrue(should_wake)
        self.assertIn("rose from 1 to 3", reason)

    def test_30_minute_rule_triggers_wake(self):
        p_worker = {
            "name": "orchestrator-codex",
            "role": "orchestrator",
            "pending": 2,
            "waiting": False,
        }
        # Pending stayed at 2
        p_state = {"last_pending": 2, "last_wake_ts": 1000.0}

        # Case A: 20 minutes elapsed (1200s) -> should NOT wake
        should_wake_20m, reason_20m = hub_messenger.should_wake_participant(p_worker, p_state, 2200.0)
        self.assertFalse(should_wake_20m)
        self.assertIn("Pending unchanged", reason_20m)

        # Case B: 31 minutes elapsed (1860s) -> SHOULD wake
        should_wake_31m, reason_31m = hub_messenger.should_wake_participant(p_worker, p_state, 2860.0)
        self.assertTrue(should_wake_31m)
        self.assertIn("30m elapsed", reason_31m)

    def test_hub_down_backoff_and_single_outage_log(self):
        messenger = hub_messenger.HubMessenger(
            hub_url="http://127.0.0.1:8765",
            project="tte",
            token_file=self.token_path,
            config_path=self.config_path,
            state_path=self.state_path,
            log_path=self.log_path,
            interval=60,
            dry_run=True,
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            import urllib.error
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            # First poll: logs outage
            delay1 = messenger.run_poll_cycle()
            self.assertTrue(messenger.hub_down)
            self.assertEqual(delay1, 120)

            # Second poll: still down, does NOT log duplicate outage
            delay2 = messenger.run_poll_cycle()
            self.assertTrue(messenger.hub_down)
            self.assertEqual(delay2, 240)

        # Inspect log file: outage must be logged only once
        log_text = self.log_path.read_text(encoding="utf-8")
        outage_count = log_text.count("Hub connection failed")
        self.assertEqual(outage_count, 1)

    def test_state_file_restart_prevents_duplicate_wakes(self):
        canned_data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        # Instance 1: runs first poll cycle
        m1 = hub_messenger.HubMessenger(
            hub_url="http://127.0.0.1:8765",
            project="tte",
            token_file=self.token_path,
            config_path=self.config_path,
            state_path=self.state_path,
            log_path=self.log_path,
            interval=60,
            dry_run=True,
        )
        with patch.object(m1, "fetch_participants", return_value=canned_data):
            m1.run_poll_cycle()

        self.assertTrue(self.state_path.exists())
        saved_state = json.loads(self.state_path.read_text(encoding="utf-8"))
        codex_state = saved_state["participants"].get("orchestrator-codex")
        self.assertIsNotNone(codex_state)
        self.assertEqual(codex_state["last_pending"], 2)
        initial_wake_ts = codex_state["last_wake_ts"]
        self.assertGreater(initial_wake_ts, 0.0)

        # Instance 2 (restart): loads state from disk, runs second cycle 5 seconds later
        logger = logging.getLogger("hub-messenger")
        for h in list(logger.handlers):
            h.close()
        logger.handlers.clear()

        m2 = hub_messenger.HubMessenger(
            hub_url="http://127.0.0.1:8765",
            project="tte",
            token_file=self.token_path,
            config_path=self.config_path,
            state_path=self.state_path,
            log_path=self.log_path,
            interval=60,
            dry_run=True,
        )

        with patch.object(m2, "fetch_participants", return_value=canned_data):
            with patch.object(m2, "launch_wake") as mock_wake:
                m2.run_poll_cycle()
                # orchestrator-codex had pending: 2, same as state; <30m elapsed -> must NOT wake
                self.assertFalse(mock_wake.called)

    def test_token_string_never_appears_in_logs_or_output(self):
        m = hub_messenger.HubMessenger(
            hub_url="http://127.0.0.1:8765",
            project="tte",
            token_file=self.token_path,
            config_path=self.config_path,
            state_path=self.state_path,
            log_path=self.log_path,
            interval=60,
            dry_run=True,
        )

        canned_data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            with patch.object(m, "fetch_participants", return_value=canned_data):
                m.run_poll_cycle()

        # Check logs and stdout
        log_content = self.log_path.read_text(encoding="utf-8")
        stdout_content = stdout_buf.getvalue()

        self.assertNotIn(self.fake_secret, log_content)
        self.assertNotIn(self.fake_secret, stdout_content)

        # Check error reporting on 401 HTTP error
        with patch("urllib.request.urlopen") as mock_open:
            import urllib.error
            mock_open.side_effect = urllib.error.HTTPError(
                "http://127.0.0.1:8765/participants?project=tte",
                401,
                "Unauthorized",
                {},
                None,
            )
            m.fetch_participants()

        updated_log = self.log_path.read_text(encoding="utf-8")
        self.assertNotIn(self.fake_secret, updated_log)
        # Log should mention the token path, never the token string
        self.assertIn("fake.token", updated_log)

    def test_no_concurrent_wakes_for_same_target(self):
        m = hub_messenger.HubMessenger(
            hub_url="http://127.0.0.1:8765",
            project="tte",
            token_file=self.token_path,
            config_path=self.config_path,
            state_path=self.state_path,
            log_path=self.log_path,
            interval=60,
            dry_run=False,
        )

        # Simulate an active process still running
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_proc.pid = 4321
        m.active_wakes["test-target"] = (mock_proc, time.monotonic(), 30)

        # Attempt to launch another wake
        target_cfg = {"mode": "codex", "thread_id": "thread-123"}
        with patch("subprocess.Popen") as mock_popen:
            m.launch_wake("test-target", target_cfg)
            self.assertFalse(mock_popen.called)

        log_content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("Skipping wake for 'test-target': previous wake process is still active", log_content)

    def test_default_wake_timeout_900_and_timeout_terminates_turn(self):
        m = hub_messenger.HubMessenger(
            hub_url="http://127.0.0.1:8765",
            project="tte",
            token_file=self.token_path,
            config_path=self.config_path,
            state_path=self.state_path,
            log_path=self.log_path,
            dry_run=False,
        )
        self.assertEqual(hub_messenger.DEFAULT_WAKE_TIMEOUT, 900)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 7890
        # Started 901 seconds ago
        m.active_wakes["stalled-target"] = (mock_proc, time.monotonic() - 901, 900)

        m.poll_active_wakes()
        self.assertTrue(mock_proc.terminate.called)
        self.assertNotIn("stalled-target", m.active_wakes)
        log_text = self.log_path.read_text(encoding="utf-8")
        self.assertIn("timed out after 900s", log_text)
        self.assertIn("Terminating turn in progress", log_text)

    def test_wake_command_line_and_ids_never_logged(self):
        m = hub_messenger.HubMessenger(
            hub_url="http://127.0.0.1:8765",
            project="tte",
            token_file=self.token_path,
            config_path=self.config_path,
            state_path=self.state_path,
            log_path=self.log_path,
            dry_run=False,
        )

        secret_thread = "thread-uuid-SECRET-HANDLE-12345"
        target_cfg = {"mode": "codex", "thread_id": secret_thread}

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 1111
            mock_popen.return_value = mock_proc
            m.launch_wake("codex-worker", target_cfg)

        log_text = self.log_path.read_text(encoding="utf-8")
        # Mode and target name are logged
        self.assertIn("Launching detached wake for 'codex-worker' [mode=codex]", log_text)
        # Thread ID and full command line are NEVER logged
        self.assertNotIn(secret_thread, log_text)
        self.assertNotIn("exec resume", log_text)

    def test_single_instance_pidfile_guard_and_stale_takeover(self):
        pid_file = self.base_dir / "test_messenger.pid"
        lock1 = hub_messenger.MessengerPidLock(pid_file)
        lock1.acquire()
        self.assertTrue(lock1.acquired)
        self.assertTrue(pid_file.exists())

        # Second instance trying to acquire same pidfile while live PID runs must raise RuntimeError
        lock2 = hub_messenger.MessengerPidLock(pid_file)
        with self.assertRaises(RuntimeError) as ctx:
            lock2.acquire()
        self.assertIn("Another hub-messenger instance is already running", str(ctx.exception))

        # Release first lock
        lock1.release()
        self.assertFalse(pid_file.exists())

        # Now simulate a stale lock (PID 999999, dead)
        stale_data = {
            "pid": 999999,
            "creation_time": 100.0,
            "start_time": 1000.0,
            "start_time_iso": "2026-01-01 00:00:00",
        }
        pid_file.write_text(json.dumps(stale_data), encoding="utf-8")

        # Second instance must detect stale dead PID and successfully acquire
        lock3 = hub_messenger.MessengerPidLock(pid_file)
        lock3.acquire()
        self.assertTrue(lock3.acquired)
        curr_data = json.loads(pid_file.read_text(encoding="utf-8"))
        import os
        self.assertEqual(curr_data["pid"], os.getpid())
        lock3.release()

    def test_missing_or_locked_token_file_does_not_crash_and_logs_once(self):
        missing_token = self.base_dir / "nonexistent.token"
        m = hub_messenger.HubMessenger(
            hub_url="http://127.0.0.1:8765",
            project="tte",
            token_file=missing_token,
            config_path=self.config_path,
            state_path=self.state_path,
            log_path=self.log_path,
            interval=60,
            dry_run=True,
        )

        # Cycle 1: Missing token file logs once and returns backoff delay without crashing
        delay1 = m.run_poll_cycle()
        self.assertTrue(m.hub_down)
        self.assertTrue(m.token_error_logged)
        self.assertEqual(delay1, 120)

        # Cycle 2: Does NOT log duplicate token error
        delay2 = m.run_poll_cycle()
        self.assertEqual(delay2, 240)

        log_text = self.log_path.read_text(encoding="utf-8")
        self.assertEqual(log_text.count("Cannot read token file"), 1)
        self.assertIn("nonexistent.token", log_text)

    def test_http_401_logs_once_and_backs_off(self):
        m = hub_messenger.HubMessenger(
            hub_url="http://127.0.0.1:8765",
            project="tte",
            token_file=self.token_path,
            config_path=self.config_path,
            state_path=self.state_path,
            log_path=self.log_path,
            interval=60,
            dry_run=True,
        )

        with patch("urllib.request.urlopen") as mock_open:
            import urllib.error
            mock_open.side_effect = urllib.error.HTTPError(
                "http://127.0.0.1:8765/v1/participants?project=tte",
                401,
                "Unauthorized",
                {},
                None,
            )
            # Cycle 1: logs HTTP 401 error
            delay1 = m.run_poll_cycle()
            self.assertTrue(m.hub_down)
            self.assertTrue(m.auth_failed)
            self.assertEqual(delay1, 120)

            # Cycle 2: backs off without duplicate log
            delay2 = m.run_poll_cycle()
            self.assertEqual(delay2, 240)

        log_text = self.log_path.read_text(encoding="utf-8")
        self.assertEqual(log_text.count("Authentication failed (HTTP 401)"), 1)

    def test_config_type_validation(self):
        # Mode not a string
        valid1, err1 = hub_messenger.validate_target_config("target-bad-mode", {"mode": 123})
        self.assertFalse(valid1)
        self.assertIn("must be a string", err1)

        # Timeout not an int
        valid2, err2 = hub_messenger.validate_target_config("target-bad-timeout", {"mode": "log", "timeout": "not-a-number"})
        self.assertFalse(valid2)
        self.assertIn("must be an integer", err2)

        # Valid config
        valid3, err3 = hub_messenger.validate_target_config("target-ok", {"mode": "codex", "timeout": 600})
        self.assertTrue(valid3)
        self.assertIsNone(err3)

    def test_stdin_devnull_and_shutil_which_and_reject_hyphen_ids(self):
        m = hub_messenger.HubMessenger(
            hub_url="http://127.0.0.1:8765",
            project="tte",
            token_file=self.token_path,
            config_path=self.config_path,
            state_path=self.state_path,
            log_path=self.log_path,
            dry_run=False,
        )

        # 1. Hyphen thread_id rejected
        with patch("subprocess.Popen") as mock_popen:
            m.launch_wake("codex-bad", {"mode": "codex", "thread_id": "-injected-flag"})
            self.assertFalse(mock_popen.called)
        log_text = self.log_path.read_text(encoding="utf-8")
        self.assertIn("cannot start with '-'", log_text)

        # 2. Valid codex wake sets stdin=DEVNULL and resolves shutil.which
        with patch("shutil.which", return_value="C:/npm/codex.cmd") as mock_which:
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.pid = 9911
                mock_popen.return_value = mock_proc

                m.launch_wake("codex-good", {"mode": "codex", "thread_id": "thread-abc"})
                self.assertTrue(mock_which.called)
                self.assertTrue(mock_popen.called)
                args, kwargs = mock_popen.call_args
                import subprocess
                self.assertEqual(kwargs.get("stdin"), subprocess.DEVNULL)
                self.assertEqual(args[0][0], "C:/npm/codex.cmd")
                self.assertEqual(args[0][3], "thread-abc")


if __name__ == "__main__":
    unittest.main()

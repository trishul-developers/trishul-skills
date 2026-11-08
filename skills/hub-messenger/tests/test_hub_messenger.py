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


if __name__ == "__main__":
    unittest.main()

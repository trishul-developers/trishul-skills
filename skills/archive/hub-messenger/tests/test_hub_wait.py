#!/usr/bin/env python3
"""Unit tests for hub_wait.py: self-wake waiter for Trishul Agent Hub participants."""

import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import hub_messenger  # noqa: E402
import hub_wait  # noqa: E402


class TestHubWait(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.token_file = self.base_dir / "test.token"
        self.secret_token = "SECRET_TOKEN_HUB_WAIT_998877"
        self.token_file.write_text(self.secret_token, encoding="utf-8")
        self.lock_dir = self.base_dir / "locks"
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_pending_0_then_2_exits_0(self):
        """Participant has pending 0 on poll 1, pending 2 on poll 2 -> exits 0 with one line."""
        poll_count = [0]

        def mock_query(hub_url, project, token, timeout=15):
            poll_count[0] += 1
            if poll_count[0] == 1:
                return [{"name": "worker-1", "pending": 0}], project, None
            return [{"name": "worker-1", "pending": 2}], project, None

        clock = [100.0]

        def fake_mono():
            clock[0] += 5.0
            return clock[0]

        out = io.StringIO()
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out):
            code = hub_wait.run_hub_wait(
                participant="worker-1",
                project="trishul-tactical-engine",
                hub_url="http://127.0.0.1:8765",
                token_file=self.token_file,
                interval=5,
                lock_dir=self.lock_dir,
                monotonic_fn=fake_mono,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 0)
        self.assertEqual(poll_count[0], 2)
        expected_line = (
            "hub_wait: worker-1 has 2 pending message(s). Read your hub inbox, then start hub_wait again.\n"
        )
        self.assertEqual(out.getvalue(), expected_line)

    def test_participant_missing_exits_3(self):
        """Participant not in the listing -> exits 3 naming participant."""
        def mock_query(hub_url, project, token, timeout=15):
            return [{"name": "other-agent", "pending": 5}], project, None

        out = io.StringIO()
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out):
            code = hub_wait.run_hub_wait(
                participant="worker-missing",
                project="trishul-tactical-engine",
                hub_url="http://127.0.0.1:8765",
                token_file=self.token_file,
                interval=5,
                lock_dir=self.lock_dir,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 3)
        self.assertIn("hub_wait: participant 'worker-missing' not found in project 'trishul-tactical-engine'.", out.getvalue())

    def test_case_sensitive_participant_match(self):
        """Participant matching is strictly case-sensitive, matching the hub's behavior."""
        def mock_query(hub_url, project, token, timeout=15):
            return [{"name": "Worker-A", "pending": 2}], project, None

        out = io.StringIO()
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out):
            code = hub_wait.run_hub_wait(
                participant="worker-a",  # Lowercase, listing has 'Worker-A'
                project="trishul-tactical-engine",
                hub_url="http://127.0.0.1:8765",
                token_file=self.token_file,
                interval=5,
                lock_dir=self.lock_dir,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 3)
        self.assertIn("participant 'worker-a' not found in project 'trishul-tactical-engine'.", out.getvalue())

    def test_max_wait_reached_exits_0(self):
        """When max-wait is reached -> exits 0 with re-arm line."""
        clock = [1000.0]

        def fake_mono():
            # Advance clock past max_wait (60s) on second call
            val = clock[0]
            clock[0] += 35.0
            return val

        def mock_query(hub_url, project, token, timeout=15):
            return [{"name": "worker-1", "pending": 0}], project, None

        out = io.StringIO()
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out):
            code = hub_wait.run_hub_wait(
                participant="worker-1",
                project="trishul-tactical-engine",
                hub_url="http://127.0.0.1:8765",
                token_file=self.token_file,
                interval=5,
                max_wait=60,
                lock_dir=self.lock_dir,
                monotonic_fn=fake_mono,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 0)
        self.assertIn("hub_wait: no mail after", out.getvalue())
        self.assertIn("Start hub_wait again.", out.getvalue())

    def test_hub_down_then_mail_quiet_until_mail(self):
        """Temporary hub downtime writes nothing to stdout/stderr; exits 0 once mail arrives."""
        poll_count = [0]

        def mock_query(hub_url, project, token, timeout=15):
            poll_count[0] += 1
            if poll_count[0] <= 3:
                return None, project, urllib.error.URLError("Connection refused")
            return [{"name": "worker-1", "pending": 1}], project, None

        clock = [100.0]

        def fake_mono():
            clock[0] += 10.0  # Total elapsed ~40s, well below 10m
            return clock[0]

        out = io.StringIO()
        err = io.StringIO()
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out), patch("sys.stderr", err):
            code = hub_wait.run_hub_wait(
                participant="worker-1",
                project="trishul-tactical-engine",
                hub_url="http://127.0.0.1:8765",
                token_file=self.token_file,
                interval=5,
                lock_dir=self.lock_dir,
                monotonic_fn=fake_mono,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(code, 0)
        self.assertEqual(poll_count[0], 4)
        # Stderr must remain completely quiet during outages under 10 minutes
        self.assertEqual(err.getvalue(), "")
        # Stdout has only the single wake message
        self.assertEqual(
            out.getvalue(),
            "hub_wait: worker-1 has 1 pending message(s). Read your hub inbox, then start hub_wait again.\n",
        )

    def test_ten_minute_warning_appears_once(self):
        """Persistent failure triggers warning after 10m (600s), logged exactly once."""
        clock = [0.0]

        def fake_mono():
            # First few calls at 0s, 300s, 605s (triggers warning), 700s, 800s, then break via max_wait
            return clock[0]

        def fake_sleep(sec):
            clock[0] += sec

        def mock_query(hub_url, project, token, timeout=15):
            return None, project, urllib.error.URLError("Connection refused")

        out = io.StringIO()
        err = io.StringIO()
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out), patch("sys.stderr", err):
            code = hub_wait.run_hub_wait(
                participant="worker-1",
                project="trishul-tactical-engine",
                hub_url="http://127.0.0.1:8765",
                token_file=self.token_file,
                interval=30,
                max_wait=1200,  # 20 minutes total
                lock_dir=self.lock_dir,
                monotonic_fn=fake_mono,
                sleep_fn=fake_sleep,
            )

        self.assertEqual(code, 0)
        err_output = err.getvalue()
        self.assertIn("hub_wait: warning: persistent hub/token failure", err_output)
        self.assertEqual(err_output.count("hub_wait: warning:"), 1)

    def test_second_waiter_same_participant_exits_4_and_other_participant_unblocked(self):
        """A second waiter for the same participant exits 4; another participant's waiter is unblocked."""
        lock_file_1 = self.lock_dir / "hub_wait.worker-1.lock"
        holder_lock = hub_messenger.OSLock(lock_file_1)
        self.assertTrue(holder_lock.try_acquire())
        holder_lock.write_diagnostics({"pid": 12345, "participant": "worker-1"})

        try:
            # Second waiter for worker-1
            out = io.StringIO()
            with patch("sys.stdout", out):
                code = hub_wait.run_hub_wait(
                    participant="worker-1",
                    project="trishul-tactical-engine",
                    hub_url="http://127.0.0.1:8765",
                    token_file=self.token_file,
                    lock_dir=self.lock_dir,
                )
            self.assertEqual(code, 4)
            self.assertEqual(out.getvalue().strip(), "hub_wait: already waiting for worker-1 (pid 12345)")

            # Waiter for different participant (worker-2) is NOT blocked
            def mock_query(hub_url, project, token, timeout=15):
                return [{"name": "worker-2", "pending": 1}], project, None

            out2 = io.StringIO()
            with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out2):
                code2 = hub_wait.run_hub_wait(
                    participant="worker-2",
                    project="trishul-tactical-engine",
                    hub_url="http://127.0.0.1:8765",
                    token_file=self.token_file,
                    lock_dir=self.lock_dir,
                )
            self.assertEqual(code2, 0)
            self.assertIn("worker-2 has 1 pending message(s)", out2.getvalue())
        finally:
            holder_lock.release()

    def test_killed_waiter_lock_file_does_not_block(self):
        """A lock file left behind by a dead waiter process does not block new acquisitions."""
        lock_file = self.lock_dir / "hub_wait.worker-dead.lock"
        # Simulate diagnostics file left on disk after killed process
        dead_diag = {"pid": 999999, "participant": "worker-dead", "start_time": 100.0}
        lock_file.write_text(json.dumps(dead_diag), encoding="utf-8")
        self.assertTrue(lock_file.exists())

        def mock_query(hub_url, project, token, timeout=15):
            return [{"name": "worker-dead", "pending": 3}], project, None

        out = io.StringIO()
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out):
            code = hub_wait.run_hub_wait(
                participant="worker-dead",
                project="trishul-tactical-engine",
                hub_url="http://127.0.0.1:8765",
                token_file=self.token_file,
                lock_dir=self.lock_dir,
            )

        self.assertEqual(code, 0)
        self.assertIn("worker-dead has 3 pending message(s)", out.getvalue())

    def test_max_wait_capped_sleep_no_overshoot_during_backoff(self):
        """Sleep duration is capped to remaining time, preventing max-wait overshoot during backoff."""
        clock = [100.0]
        sleep_durations = []

        def fake_mono():
            return clock[0]

        def fake_sleep(sec):
            sleep_durations.append(sec)
            clock[0] += sec

        # Continual error so backoff triggers (starts at 30s)
        def mock_query(hub_url, project, token, timeout=15):
            return None, project, urllib.error.URLError("Connection refused")

        out = io.StringIO()
        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out):
            code = hub_wait.run_hub_wait(
                participant="worker-1",
                project="trishul-tactical-engine",
                hub_url="http://127.0.0.1:8765",
                token_file=self.token_file,
                interval=30,
                max_wait=45,  # 45s total: first sleep 30s, second sleep capped at 15s!
                lock_dir=self.lock_dir,
                monotonic_fn=fake_mono,
                sleep_fn=fake_sleep,
            )

        self.assertEqual(code, 0)
        # Total elapsed time must be exactly 45s (no overshoot to 60s or 90s)
        self.assertEqual(clock[0] - 100.0, 45.0)
        self.assertEqual(sleep_durations, [30, 15.0])
        self.assertIn("hub_wait: no mail after 45 s. Start hub_wait again.", out.getvalue())

    def test_killed_real_lock_holder_process_allows_immediate_acquire(self):
        """A killed real lock-holder process drops OS lock and allows a new process to acquire immediately."""
        import subprocess
        lock_file = self.lock_dir / "hub_wait.worker-real.lock"
        ready_file = self.base_dir / "worker_real.ready"

        code = (
            "import sys, time\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {str(SCRIPT_DIR)!r})\n"
            "import hub_messenger\n"
            f"lock = hub_messenger.OSLock(Path({str(lock_file)!r}))\n"
            "assert lock.try_acquire()\n"
            "lock.write_diagnostics({'pid': 98765, 'participant': 'worker-real'})\n"
            f"Path({str(ready_file)!r}).write_text('READY', encoding='utf-8')\n"
            "while True:\n"
            "    time.sleep(0.1)\n"
        )

        proc = subprocess.Popen([sys.executable, "-c", code])
        try:
            t0 = time.time()
            while not ready_file.exists() and time.time() - t0 < 10:
                time.sleep(0.05)
            self.assertTrue(ready_file.exists(), "Holder process did not start in time")

            # While child holds lock, waiter exits 4
            out = io.StringIO()
            with patch("sys.stdout", out):
                code_wait = hub_wait.run_hub_wait(
                    participant="worker-real",
                    project="trishul-tactical-engine",
                    hub_url="http://127.0.0.1:8765",
                    token_file=self.token_file,
                    lock_dir=self.lock_dir,
                )
            self.assertEqual(code_wait, 4)
            self.assertIn("already waiting for worker-real", out.getvalue())

            # Kill the holder process
            proc.terminate()
            proc.wait(timeout=5)

            # Now a new waiter acquires the lock at once and succeeds
            def mock_query(hub_url, project, token, timeout=15):
                return [{"name": "worker-real", "pending": 1}], project, None

            out2 = io.StringIO()
            with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out2):
                code_after_kill = hub_wait.run_hub_wait(
                    participant="worker-real",
                    project="trishul-tactical-engine",
                    hub_url="http://127.0.0.1:8765",
                    token_file=self.token_file,
                    lock_dir=self.lock_dir,
                )
            self.assertEqual(code_after_kill, 0)
            self.assertIn("worker-real has 1 pending message(s)", out2.getvalue())
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def test_token_string_never_appears_in_output_or_files(self):
        """Bearer token secret must never appear in stdout, stderr, or any lock/diagnostic file."""
        out = io.StringIO()
        err = io.StringIO()

        # Run with auth failure
        def mock_query(hub_url, project, token, timeout=15):
            return None, project, urllib.error.HTTPError(
                url="http://127.0.0.1:8765/participants",
                code=401,
                msg="Unauthorized",
                hdrs=None,
                fp=None,
            )

        clock = [0.0]

        def fake_mono():
            clock[0] += 700.0
            return clock[0]

        with patch("hub_wait.query_participants", side_effect=mock_query), patch("sys.stdout", out), patch("sys.stderr", err):
            hub_wait.run_hub_wait(
                participant="worker-token",
                project="trishul-tactical-engine",
                hub_url="http://127.0.0.1:8765",
                token_file=self.token_file,
                interval=5,
                max_wait=10,
                lock_dir=self.lock_dir,
                monotonic_fn=fake_mono,
                sleep_fn=lambda _: None,
            )

        self.assertNotIn(self.secret_token, out.getvalue())
        self.assertNotIn(self.secret_token, err.getvalue())

        for p in self.base_dir.rglob("*"):
            if p.is_file() and p != self.token_file:
                content = p.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn(self.secret_token, content)

    def test_base_dir_default_and_localappdata_config_fallback(self):
        """Default base directory is ~/.hub-messenger and %LOCALAPPDATA% config fallback works."""
        base_dir = hub_messenger.get_default_base_dir()
        self.assertEqual(base_dir, Path.home() / ".hub-messenger")

        # Fallback config testing
        fake_localappdata = self.base_dir / "AppDataLocal"
        fallback_dir = fake_localappdata / "hub-messenger"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback_config = fallback_dir / "config.json"
        fallback_config.write_text(
            json.dumps({"targets": {"custom-agent": {"mode": "log"}}}),
            encoding="utf-8",
        )

        missing_primary = self.base_dir / "missing" / "config.json"
        notice_logged = []

        with patch.dict(os.environ, {"LOCALAPPDATA": str(fake_localappdata)}):
            loaded = hub_messenger.load_config(
                missing_primary,
                on_fallback=lambda path: notice_logged.append(path),
            )

        self.assertIn("custom-agent", loaded.get("targets", {}))
        self.assertEqual(len(notice_logged), 1)
        self.assertEqual(notice_logged[0], str(fallback_config))


if __name__ == "__main__":
    unittest.main()

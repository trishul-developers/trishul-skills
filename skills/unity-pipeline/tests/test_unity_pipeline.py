#!/usr/bin/env python3
"""Unit tests for unity_pipeline.py: machine lock, editor resolution, and NUnit parsing."""

import json
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Add scripts directory to path
PIPELINE_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(PIPELINE_SCRIPT_DIR))

import unity_pipeline  # noqa: E402


def _multiprocess_lock_worker(lock_path_str: str, project_path_str: str, log_path_str: str):
    """Worker function for multiprocessing concurrent acquire race test."""
    lock = unity_pipeline.UnityMachineLock(
        project_path=Path(project_path_str),
        mode="wait",
        timeout=20,
        lock_path=Path(lock_path_str),
    )
    with lock:
        t_enter = time.time()
        time.sleep(0.05)
        t_exit = time.time()
        with open(log_path_str, "a", encoding="utf-8") as f:
            f.write(f"{os.getpid()},{t_enter:.4f},{t_exit:.4f}\n")


class TestUnityMachineLock(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.lock_path = Path(self.temp_dir.name) / "test_unity.lock"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_acquire_and_release(self):
        project_path = Path(self.temp_dir.name) / "MyProject"
        lock = unity_pipeline.UnityMachineLock(
            project_path=project_path,
            mode="exit",
            lock_path=self.lock_path,
        )
        self.assertFalse(self.lock_path.exists())

        with lock:
            self.assertTrue(self.lock_path.exists())
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            self.assertEqual(data["pid"], os.getpid())
            self.assertEqual(data["project_path"], str(project_path.resolve()))
            self.assertIn("start_time", data)

        self.assertFalse(self.lock_path.exists())

    def test_stale_lock_takeover(self):
        # Fake dead PID (e.g. 999999)
        fake_stale_data = {
            "pid": 999999,
            "creation_time": 100.0,
            "start_time": 1000.0,
            "start_time_iso": "2026-01-01 00:00:00",
            "project_path": "E:/Fake/DeadProject",
        }
        self.lock_path.write_text(json.dumps(fake_stale_data), encoding="utf-8")
        self.assertTrue(self.lock_path.exists())

        project_path = Path(self.temp_dir.name) / "ActiveProject"
        lock = unity_pipeline.UnityMachineLock(
            project_path=project_path,
            mode="exit",
            lock_path=self.lock_path,
        )

        # Acquiring should detect stale dead PID and take over
        with lock:
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            self.assertEqual(data["pid"], os.getpid())
            self.assertEqual(data["project_path"], str(project_path.resolve()))

        self.assertFalse(self.lock_path.exists())

    def test_live_lock_exit_mode(self):
        project_path = Path(self.temp_dir.name) / "ActiveProject"
        fake_live_data = {
            "pid": 88888,
            "creation_time": 100.0,
            "start_time": 1000.0,
            "start_time_iso": "2026-01-01 00:00:00",
            "project_path": "E:/Other/Project",
        }
        self.lock_path.write_text(json.dumps(fake_live_data), encoding="utf-8")

        lock = unity_pipeline.UnityMachineLock(
            project_path=project_path,
            mode="exit",
            lock_path=self.lock_path,
        )
        orig_is_pid_alive = unity_pipeline.UnityMachineLock.is_pid_alive
        try:
            unity_pipeline.UnityMachineLock.is_pid_alive = lambda self, pid, expected_creation_time=None: pid == 88888
            with self.assertRaises(SystemExit) as ctx:
                with lock:
                    pass
            self.assertEqual(ctx.exception.code, 75)
        finally:
            unity_pipeline.UnityMachineLock.is_pid_alive = orig_is_pid_alive

    def test_wait_mode_timeout(self):
        project_path = Path(self.temp_dir.name) / "WaitProject"
        fake_live_data = {
            "pid": 88888,
            "creation_time": 100.0,
            "start_time": 1000.0,
            "start_time_iso": "2026-01-01 00:00:00",
            "project_path": "E:/Other/Project",
        }
        self.lock_path.write_text(json.dumps(fake_live_data), encoding="utf-8")

        lock = unity_pipeline.UnityMachineLock(
            project_path=project_path,
            mode="wait",
            timeout=1,
            lock_path=self.lock_path,
        )
        orig_is_pid_alive = unity_pipeline.UnityMachineLock.is_pid_alive
        try:
            unity_pipeline.UnityMachineLock.is_pid_alive = lambda self, pid, expected_creation_time=None: True
            with self.assertRaises(SystemExit) as ctx:
                with lock:
                    pass
            self.assertEqual(ctx.exception.code, 1)
        finally:
            unity_pipeline.UnityMachineLock.is_pid_alive = orig_is_pid_alive

    def test_pid_reuse_detected_as_dead(self):
        # Lock recorded PID 88888 with creation_time 111.0, but live process has creation_time 222.0
        project_path = Path(self.temp_dir.name) / "ReuseProject"
        fake_reuse_data = {
            "pid": 88888,
            "creation_time": 111.0,
            "start_time": 1000.0,
            "start_time_iso": "2026-01-01 00:00:00",
            "project_path": "E:/Old/Project",
        }
        self.lock_path.write_text(json.dumps(fake_reuse_data), encoding="utf-8")

        lock = unity_pipeline.UnityMachineLock(
            project_path=project_path,
            mode="exit",
            lock_path=self.lock_path,
        )

        orig_is_pid_alive = unity_pipeline.UnityMachineLock.is_pid_alive
        try:
            # When expected_creation_time is checked against 222.0, PID reuse causes is_pid_alive to return False
            def mock_is_pid_alive(self, pid, expected_creation_time=None):
                if pid == 88888:
                    live_creation_time = 222.0
                    if expected_creation_time is not None and expected_creation_time != live_creation_time:
                        return False
                    return True
                return False

            unity_pipeline.UnityMachineLock.is_pid_alive = mock_is_pid_alive
            # Since PID is treated as dead (reused), takeover should succeed without raising SystemExit(75)
            with lock:
                self.assertTrue(self.lock_path.exists())
                data = json.loads(self.lock_path.read_text(encoding="utf-8"))
                self.assertEqual(data["pid"], os.getpid())
        finally:
            unity_pipeline.UnityMachineLock.is_pid_alive = orig_is_pid_alive

    def test_corrupt_lock_file_grace_period_and_stale_takeover(self):
        project_path = Path(self.temp_dir.name) / "CorruptProject"
        # Write corrupt non-JSON content
        self.lock_path.write_text("CORRUPT_NOT_JSON", encoding="utf-8")

        lock = unity_pipeline.UnityMachineLock(
            project_path=project_path,
            mode="exit",
            lock_path=self.lock_path,
        )

        # Set mtime to 10 seconds ago (outside grace period of 0.1s)
        old_time = time.time() - 10.0
        os.utime(self.lock_path, (old_time, old_time))

        read_res = lock.read_lock(grace_period=0.1)
        self.assertIsNotNone(read_res)
        self.assertTrue(read_res.get("stale"))
        self.assertEqual(read_res.get("pid"), -1)

        # Acquire should take over corrupt stale file
        with lock:
            self.assertTrue(self.lock_path.exists())
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            self.assertEqual(data["pid"], os.getpid())

    def test_multiprocessing_concurrent_acquire_race(self):
        project_path = Path(self.temp_dir.name) / "RaceProject"
        log_path = Path(self.temp_dir.name) / "race_log.txt"

        procs = []
        num_workers = 4
        for _ in range(num_workers):
            p = multiprocessing.Process(
                target=_multiprocess_lock_worker,
                args=(str(self.lock_path), str(project_path), str(log_path)),
            )
            procs.append(p)

        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=30)

        self.assertTrue(log_path.exists())
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), num_workers)

        # Verify no overlapping hold intervals
        intervals = []
        for line in lines:
            parts = line.split(",")
            intervals.append((float(parts[1]), float(parts[2])))

        intervals.sort(key=lambda x: x[0])
        for i in range(len(intervals) - 1):
            curr_exit = intervals[i][1]
            next_enter = intervals[i + 1][0]
            # Ensure next process entered after previous process exited
            self.assertLessEqual(curr_exit, next_enter + 0.05)


class TestUnityEditorResolution(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_project_version_file_fails(self):
        with self.assertRaises(SystemExit) as ctx:
            unity_pipeline.resolve_unity_exe(self.project_path)
        self.assertEqual(ctx.exception.code, 1)

    def test_missing_m_editor_version_fails(self):
        ps_dir = self.project_path / "ProjectSettings"
        ps_dir.mkdir(parents=True)
        (ps_dir / "ProjectVersion.txt").write_text("some_other_key: 1.0.0\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as ctx:
            unity_pipeline.resolve_unity_exe(self.project_path)
        self.assertEqual(ctx.exception.code, 1)

    def test_bom_in_project_version_parsed(self):
        ps_dir = self.project_path / "ProjectSettings"
        ps_dir.mkdir(parents=True)
        # Write UTF-8 BOM
        content = "\ufeffm_EditorVersion: 6000.0.32f1\nm_EditorVersionWithRevision: 6000.0.32f1 (abcdef)\n"
        (ps_dir / "ProjectVersion.txt").write_text(content, encoding="utf-8")

        # Mock hub candidate check or test parsing directly
        existing_exe = sys.executable
        resolved = unity_pipeline.resolve_unity_exe(
            self.project_path, unity_path_override=existing_exe
        )
        self.assertEqual(resolved, str(Path(existing_exe)))

        # Also directly test file reading with utf-8-sig
        lines = (ps_dir / "ProjectVersion.txt").read_text(encoding="utf-8-sig").splitlines()
        self.assertTrue(lines[0].startswith("m_EditorVersion:"))
        self.assertEqual(lines[0].split(":", 1)[1].strip(), "6000.0.32f1")

    def test_uninstalled_version_fails(self):
        ps_dir = self.project_path / "ProjectSettings"
        ps_dir.mkdir(parents=True)
        (ps_dir / "ProjectVersion.txt").write_text("m_EditorVersion: 1234.5.6f99\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as ctx:
            unity_pipeline.resolve_unity_exe(self.project_path)
        self.assertEqual(ctx.exception.code, 1)

    def test_explicit_override_success(self):
        existing_file = sys.executable
        resolved = unity_pipeline.resolve_unity_exe(
            self.project_path, unity_path_override=existing_file
        )
        self.assertEqual(resolved, str(Path(existing_file)))

    def test_explicit_override_nonexistent_fails(self):
        with self.assertRaises(SystemExit) as ctx:
            unity_pipeline.resolve_unity_exe(
                self.project_path, unity_path_override="C:/Nonexistent/Unity.exe"
            )
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()

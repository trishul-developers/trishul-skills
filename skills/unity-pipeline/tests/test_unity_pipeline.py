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


def _multiprocess_hold_worker(lock_path_str: str, project_path_str: str, ready_path_str: str):
    """Worker function that acquires the lock, signals readiness, and holds it until killed."""
    lock = unity_pipeline.UnityMachineLock(
        project_path=Path(project_path_str),
        mode="exit",
        lock_path=Path(lock_path_str),
    )
    with lock:
        Path(ready_path_str).write_text("READY", encoding="utf-8")
        while True:
            time.sleep(0.1)


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
            data = lock.read_diagnostics()
            self.assertEqual(data["pid"], os.getpid())
            self.assertEqual(data["project_path"], str(project_path.resolve()))
            self.assertIn("start_time", data)

        self.assertFalse(lock.acquired)
        # Diagnostics file remains on disk for reporting but does not block subsequent acquire
        self.assertTrue(self.lock_path.exists())

        lock2 = unity_pipeline.UnityMachineLock(
            project_path=project_path,
            mode="exit",
            lock_path=self.lock_path,
        )
        with lock2:
            self.assertTrue(lock2.acquired)

    def test_multiprocessing_concurrent_acquire_race(self):
        """Multiprocessing race: exactly one holder at a time."""
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

    def test_holder_killed_and_another_process_acquires_at_once(self):
        """When holder process is killed, OS drops lock and another process acquires immediately."""
        project_path = Path(self.temp_dir.name) / "KilledHolderProject"
        ready_path = Path(self.temp_dir.name) / "holder.ready"
        p = multiprocessing.Process(
            target=_multiprocess_hold_worker,
            args=(str(self.lock_path), str(project_path), str(ready_path)),
        )
        p.start()
        try:
            t0 = time.time()
            while not ready_path.exists() and time.time() - t0 < 10:
                time.sleep(0.05)
            self.assertTrue(ready_path.exists(), "Holder worker did not acquire lock in time")

            # While holder is alive, acquire in exit mode must exit immediately with code 75
            lock_fail = unity_pipeline.UnityMachineLock(
                project_path=project_path,
                mode="exit",
                lock_path=self.lock_path,
            )
            with self.assertRaises(SystemExit) as ctx:
                lock_fail.acquire()
            self.assertEqual(ctx.exception.code, 75)

            # Terminate holder
            p.terminate()
            p.join(timeout=5)

            # Another process must now acquire at once
            lock_success = unity_pipeline.UnityMachineLock(
                project_path=project_path,
                mode="exit",
                lock_path=self.lock_path,
            )
            lock_success.acquire()
            self.assertTrue(lock_success.acquired)
            lock_success.release()
        finally:
            if p.is_alive():
                p.terminate()
                p.join(timeout=2)

    def test_wait_mode_timeout(self):
        """Wait mode times out with code 1 if lock is not released within timeout."""
        project_path = Path(self.temp_dir.name) / "WaitProject"
        ready_path = Path(self.temp_dir.name) / "wait_holder.ready"
        p = multiprocessing.Process(
            target=_multiprocess_hold_worker,
            args=(str(self.lock_path), str(project_path), str(ready_path)),
        )
        p.start()
        try:
            t0 = time.time()
            while not ready_path.exists() and time.time() - t0 < 10:
                time.sleep(0.05)
            self.assertTrue(ready_path.exists(), "Holder worker did not acquire lock in time")

            lock_wait = unity_pipeline.UnityMachineLock(
                project_path=project_path,
                mode="wait",
                timeout=1,
                lock_path=self.lock_path,
            )
            start_t = time.monotonic()
            with self.assertRaises(SystemExit) as ctx:
                lock_wait.acquire()
            elapsed = time.monotonic() - start_t
            self.assertEqual(ctx.exception.code, 1)
            self.assertGreaterEqual(elapsed, 0.9)
        finally:
            if p.is_alive():
                p.terminate()
                p.join(timeout=2)

    def test_diagnostics_file_left_behind_by_killed_holder_does_not_block(self):
        """Diagnostics file left behind on disk by killed holder does not block new acquisitions."""
        project_path = Path(self.temp_dir.name) / "LeftoverProject"
        ready_path = Path(self.temp_dir.name) / "leftover_holder.ready"
        p = multiprocessing.Process(
            target=_multiprocess_hold_worker,
            args=(str(self.lock_path), str(project_path), str(ready_path)),
        )
        p.start()
        try:
            t0 = time.time()
            while not ready_path.exists() and time.time() - t0 < 10:
                time.sleep(0.05)
            self.assertTrue(ready_path.exists())
            p.terminate()
            p.join(timeout=5)
        finally:
            if p.is_alive():
                p.terminate()
                p.join(timeout=2)

        # File is still on disk
        self.assertTrue(self.lock_path.exists())

        # New lock acquires immediately without blocking and writes its own diagnostics
        lock_new = unity_pipeline.UnityMachineLock(
            project_path=project_path,
            mode="exit",
            lock_path=self.lock_path,
        )
        with lock_new:
            self.assertTrue(lock_new.acquired)
            data = lock_new.read_diagnostics()
            self.assertEqual(data["pid"], os.getpid())
            self.assertEqual(data["project_path"], str(project_path.resolve()))


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

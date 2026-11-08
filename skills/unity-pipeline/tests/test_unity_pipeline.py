#!/usr/bin/env python3
"""Unit tests for unity_pipeline.py: machine lock, editor resolution, and NUnit parsing."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to path
PIPELINE_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(PIPELINE_SCRIPT_DIR))

import unity_pipeline  # noqa: E402


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
        # Mock is_pid_alive to return True for PID 88888
        orig_is_pid_alive = unity_pipeline.UnityMachineLock.is_pid_alive
        try:
            unity_pipeline.UnityMachineLock.is_pid_alive = lambda self, pid: pid == 88888
            with self.assertRaises(SystemExit) as ctx:
                with lock:
                    pass
            self.assertEqual(ctx.exception.code, 75)
        finally:
            unity_pipeline.UnityMachineLock.is_pid_alive = orig_is_pid_alive


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

    def test_uninstalled_version_fails(self):
        ps_dir = self.project_path / "ProjectSettings"
        ps_dir.mkdir(parents=True)
        (ps_dir / "ProjectVersion.txt").write_text("m_EditorVersion: 1234.5.6f99\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as ctx:
            unity_pipeline.resolve_unity_exe(self.project_path)
        self.assertEqual(ctx.exception.code, 1)

    def test_explicit_override_success(self):
        # If override points to an existing file (like this test file or python exe)
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

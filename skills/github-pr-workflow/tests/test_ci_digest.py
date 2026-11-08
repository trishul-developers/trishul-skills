#!/usr/bin/env python3
"""Unit tests for CI digest in gh_helper.py."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import gh_helper  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_tte_ci.log"

SAMPLE_NUNIT_XML = """<?xml version="1.0" encoding="utf-8"?>
<test-run id="2" testcasecount="50" result="Failed" total="50" passed="48" failed="2" skipped="0" duration="1.25">
  <test-suite type="TestSuite" id="1001" name="Tests" total="50" passed="48" failed="2">
    <test-case id="2001" name="SamplePlayModeTest" fullname="Trishul.Tests.PlayMode.SamplePlayModeTest" result="Failed">
      <failure>
        <message><![CDATA[Expected: True but was: False]]></message>
        <stack-trace><![CDATA[at Trishul.Tests.PlayMode.SamplePlayModeTest.Run() in /path/Test.cs:line 42]]></stack-trace>
      </failure>
    </test-case>
    <test-case id="2002" name="SampleSecondTest" fullname="Trishul.Tests.PlayMode.SampleSecondTest" result="Failed">
      <failure>
        <message><![CDATA[NullReferenceException occurred]]></message>
      </failure>
    </test-case>
  </test-suite>
</test-run>
"""


class TestCiDigest(unittest.TestCase):
    def test_strip_log_prefix(self):
        line = "Unity EditMode\tUNKNOWN STEP\t2026-11-07T01:39:50.1832275Z | total | passed |"
        clean = gh_helper.strip_log_prefix(line)
        self.assertEqual(clean, "| total | passed |")

    @patch("gh_helper.run_cmd")
    def test_parse_real_tte_ci_fixture(self, mock_run_cmd):
        self.assertTrue(FIXTURE_PATH.exists(), f"Fixture file not found: {FIXTURE_PATH}")
        fixture_content = FIXTURE_PATH.read_text(encoding="utf-8")
        mock_run_cmd.return_value = (0, fixture_content, "")

        res = gh_helper.parse_tte_ci_job_log("tosumitdhaka/trishul-tactical-engine", 42323789243, 1001)
        self.assertIsNotNone(res)
        counts = res["counts"]
        self.assertEqual(counts["total"], 3709)
        self.assertEqual(counts["passed"], 3699)
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(counts["skipped"], 9)

        # Ensure failure is parsed despite blank lines and markdown table rows
        failures = res["failures"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(
            failures[0][0],
            "Trishul.Tests.EditMode.G02Orders.LargeSelectionMoveTests.NormalSceneTearDown_ReleasesConsumerAndClearsHeldViews",
        )
        self.assertIn("Ambiguous match found", failures[0][1])

    def test_parse_nunit_artifact_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xml_file = Path(tmpdir) / "TestResults-editmode.xml"
            xml_file.write_text(SAMPLE_NUNIT_XML, encoding="utf-8")

            with patch("gh_helper.run_cmd") as mock_run_cmd:
                def fake_download(cmd):
                    dest_dir = cmd[cmd.index("--dir") + 1]
                    target = Path(dest_dir) / "TestResults-editmode.xml"
                    target.write_text(SAMPLE_NUNIT_XML, encoding="utf-8")
                    return (0, "Downloaded", "")

                mock_run_cmd.side_effect = fake_download
                res = gh_helper.parse_nunit_artifact("owner/repo", 12345, "Unity EditMode")
                self.assertIsNotNone(res)
                self.assertEqual(res["counts"]["total"], 50)
                self.assertEqual(res["counts"]["passed"], 48)
                self.assertEqual(res["counts"]["failed"], 2)
                self.assertEqual(len(res["failures"]), 2)
                self.assertEqual(res["failures"][0][0], "Trishul.Tests.PlayMode.SamplePlayModeTest")
                self.assertIn("Expected: True", res["failures"][0][1])

    def test_strict_matching_never_falls_back_to_xml_files_0(self):
        # Strict matching: unrelated xml filename must return None
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "unrelated_other.xml"
            target.write_text(SAMPLE_NUNIT_XML, encoding="utf-8")

            with patch("gh_helper.run_cmd") as mock_run_cmd:
                mock_run_cmd.return_value = (0, "Downloaded", "")
                res = gh_helper.parse_nunit_artifact("owner/repo", 12345, "Unity EditMode", target_dir=tmpdir)
                self.assertIsNone(res)

    @patch("gh_helper.parse_tte_ci_job_log")
    @patch("gh_helper.run_cmd")
    def test_ci_digest_50_line_cap_and_failed_unity_test_counts(self, mock_run, mock_parse_log):
        # 30 jobs to exceed 50 lines
        jobs = []
        for i in range(30):
            jobs.append({
                "id": 1000 + i,
                "name": f"Unity EditMode Job {i}",
                "status": "completed",
                "conclusion": "failure" if i % 2 == 0 else "success",
            })

        canned_run_info = {
            "name": "Unity CI",
            "url": "https://github.com/owner/repo/actions/runs/123",
            "headSha": "abcdef1234567890",
            "headBranch": "main",
            "status": "completed",
            "conclusion": "failure",
            "jobs": jobs,
        }

        mock_run.return_value = (0, json.dumps(canned_run_info), "")
        mock_parse_log.return_value = {
            "counts": {"total": 100, "passed": 98, "failed": 2, "skipped": 0},
            "failures": [("TestA", "Error message")],
        }

        class FakeArgs:
            repo = "owner/repo"
            run_id = 123
            branch = None
            max_failures = 5

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            gh_helper.cmd_ci_digest(FakeArgs())

        output = buf.getvalue()
        lines = output.strip().splitlines()
        self.assertLessEqual(len(lines), 50)
        self.assertTrue(any("Tests: 98 passed, 2 failed" in l for l in lines))
        self.assertTrue(any("truncated to meet 50-line cap" in l for l in lines))

    def test_api_request_failure_exits_one_line_cleanly(self):
        # Test api_request HTTPError and URLError handling with single line error and code 1
        with patch("urllib.request.urlopen") as mock_open:
            import urllib.error
            mock_open.side_effect = urllib.error.HTTPError(
                "https://api.github.com/test", 404, "Not Found", {}, io.BytesIO(b'{"message": "Resource not found"}')
            )
            with patch("gh_helper.get_token", return_value="dummy_token"):
                err_buf = io.StringIO()
                with patch("sys.stderr", err_buf):
                    with self.assertRaises(SystemExit) as ctx:
                        gh_helper.api_request("/test")
                    self.assertEqual(ctx.exception.code, 1)
                self.assertIn("ERROR: GitHub API HTTP 404", err_buf.getvalue())
                self.assertIn("Resource not found", err_buf.getvalue())
                # Must be single line (no traceback)
                self.assertEqual(len(err_buf.getvalue().strip().splitlines()), 1)

    @patch("gh_helper.get_token")
    @patch("gh_helper.run_cmd")
    def test_ci_digest_uses_gh_only_no_token_or_credential_fill(self, mock_run, mock_token):
        canned_run_info = {
            "name": "Unity CI",
            "url": "https://github.com/owner/repo/actions/runs/123",
            "headSha": "abcdef1234567890",
            "headBranch": "main",
            "status": "completed",
            "conclusion": "success",
            "jobs": [{"id": 1, "name": "Lint", "status": "completed", "conclusion": "success"}],
        }
        mock_run.return_value = (0, json.dumps(canned_run_info), "")

        class FakeArgs:
            repo = "owner/repo"
            run_id = 123
            branch = None
            max_failures = 5

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            gh_helper.cmd_ci_digest(FakeArgs())

        # Verify get_token (which invokes git credential fill) was NEVER called
        self.assertFalse(mock_token.called)

    def test_shared_digest_subparser(self):
        # Verify both commands share subparser options
        with patch("sys.argv", ["gh_helper.py", "ci-digest", "--run-id", "12345", "--max-failures", "5"]):
            with patch("gh_helper.cmd_ci_digest") as mock_ci_digest:
                gh_helper.main()
                self.assertTrue(mock_ci_digest.called)
                args = mock_ci_digest.call_args[0][0]
                self.assertEqual(args.run_id, 12345)
                self.assertEqual(args.max_failures, 5)

        with patch("sys.argv", ["gh_helper.py", "ci", "digest", "--run-id", "67890", "--max-failures", "8"]):
            with patch("gh_helper.cmd_ci_digest") as mock_ci_digest:
                gh_helper.main()
                self.assertTrue(mock_ci_digest.called)
                args = mock_ci_digest.call_args[0][0]
                self.assertEqual(args.run_id, 67890)
                self.assertEqual(args.max_failures, 8)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Unit tests for CI digest in gh_helper.py."""

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


SAMPLE_CI_LOG = """
Unity EditMode	UNKNOWN STEP	2026-11-07T01:39:50.1832275Z ### Unity EditMode
Unity EditMode	UNKNOWN STEP	2026-11-07T01:39:50.1832583Z 
Unity EditMode	UNKNOWN STEP	2026-11-07T01:39:50.1832752Z | total | passed | failed | skipped | inconclusive | minutes | unity exit |
Unity EditMode	UNKNOWN STEP	2026-11-07T01:39:50.1833067Z |---:|---:|---:|---:|---:|---:|---:|
Unity EditMode	UNKNOWN STEP	2026-11-07T01:39:50.1833269Z | 3709 | 3699 | 1 | 9 | 0 | 16 | 2 |
Unity EditMode	UNKNOWN STEP	2026-11-07T01:39:50.1833397Z 
Unity EditMode	UNKNOWN STEP	2026-11-07T01:39:50.1833481Z First failures (of 1):
Unity EditMode	UNKNOWN STEP	2026-11-07T01:39:50.1834058Z - `Trishul.Tests.EditMode.SampleTest.MyTestMethod`: System.Exception : Failed on assertion.
Unity EditMode	UNKNOWN STEP	2026-11-07T01:39:50.2077247Z ##[error]Process completed with exit code 1.
"""

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
    def test_parse_tte_ci_job_log(self, mock_run_cmd):
        mock_run_cmd.return_value = (0, SAMPLE_CI_LOG, "")
        res = gh_helper.parse_tte_ci_job_log("owner/repo", 12345, 67890)
        self.assertIsNotNone(res)
        counts = res["counts"]
        self.assertEqual(counts["total"], 3709)
        self.assertEqual(counts["passed"], 3699)
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(counts["skipped"], 9)
        failures = res["failures"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], "Trishul.Tests.EditMode.SampleTest.MyTestMethod")
        self.assertIn("Failed on assertion", failures[0][1])

    def test_parse_nunit_artifact_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xml_file = Path(tmpdir) / "editmode.xml"
            xml_file.write_text(SAMPLE_NUNIT_XML, encoding="utf-8")

            with patch("gh_helper.run_cmd") as mock_run_cmd:
                def fake_download(cmd):
                    # simulate downloading into tmpdir
                    dest_dir = cmd[cmd.index("--dir") + 1]
                    target = Path(dest_dir) / "test-results.xml"
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


if __name__ == "__main__":
    unittest.main()

import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import check_quota  # noqa: E402


class TestAgyQuota(unittest.TestCase):
    def test_parse_models_handles_nulls(self):
        raw = {
            "userStatus": {
                "planStatus": None,
                "cascadeModelConfigData": None,
            }
        }
        self.assertEqual(check_quota.parse_models(raw), [])

    def test_fetch_user_status_preserves_scheme(self):
        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"userStatus": {}}'

        def fake_urlopen(req, timeout=5.0):
            captured["url"] = req.full_url
            return FakeResp()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            check_quota.fetch_user_status("https://127.0.0.1:46627/", "tok")
        self.assertEqual(
            captured["url"],
            "https://127.0.0.1:46627/exa.language_server_pb.LanguageServerService/GetUserStatus",
        )

    def test_json_models_only_empty_models_no_index_error(self):
        raw = {
            "userStatus": {
                "planStatus": None,
                "cascadeModelConfigData": {"clientModelConfigs": []},
            }
        }
        stdout = io.StringIO()
        with (
            patch.dict(os.environ, {"ANTIGRAVITY_LS_ADDRESS": "127.0.0.1:46627"}),
            patch.object(check_quota, "fetch_user_status", return_value=raw),
            patch.object(sys, "argv", ["check_quota.py", "--models-only", "-f", "json"]),
            patch.object(sys, "stdout", stdout),
        ):
            check_quota.main()
        self.assertEqual(json.loads(stdout.getvalue()), [])

    def test_quiet_without_model_or_credits_only(self):
        raw = {
            "userStatus": {
                "planStatus": {"availablePromptCredits": 10, "availableFlowCredits": 20},
                "cascadeModelConfigData": {
                    "clientModelConfigs": [
                        {
                            "label": "Gemini Flash",
                            "modelId": "gemini-flash",
                            "quotaInfo": {"remainingFraction": 0.75},
                        }
                    ]
                },
            }
        }
        stdout = io.StringIO()
        with (
            patch.dict(os.environ, {"ANTIGRAVITY_LS_ADDRESS": "127.0.0.1:46627"}),
            patch.object(check_quota, "fetch_user_status", return_value=raw),
            patch.object(sys, "argv", ["check_quota.py", "-f", "quiet"]),
            patch.object(sys, "stdout", stdout),
        ):
            check_quota.main()
        self.assertEqual(stdout.getvalue().strip(), "gemini-flash: 75.00%")

    def test_run_via_agy_windows_quoting(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

        args = check_quota.argparse.Namespace(
            model="claude sonnet",
            format="json",
            credits_only=False,
            models_only=False,
            all=False,
        )
        with (
            patch.object(check_quota.shutil, "which", return_value="agy"),
            patch.object(check_quota.os, "name", "nt"),
            patch.object(check_quota.subprocess, "run", side_effect=fake_run),
        ):
            rc = check_quota.run_via_agy(args)
        self.assertEqual(rc, 0)
        prompt_arg = captured["cmd"][1]
        self.assertIn('"claude sonnet"', prompt_arg)


if __name__ == "__main__":
    unittest.main()

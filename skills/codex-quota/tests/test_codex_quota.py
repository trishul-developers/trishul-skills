import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import check_codex_quota  # noqa: E402


class TestCodexQuota(unittest.TestCase):
    def test_format_window_none(self):
        res = check_codex_quota.format_window(None)
        self.assertEqual(res["used"], "N/A")
        self.assertEqual(res["remaining"], "N/A")
        self.assertNotIn("windowDurationMins", res)

    def test_format_table_missing_primary_and_none_display_name(self):
        account = {"planType": "plus", "email": "user@example.com"}
        rate_limits = {"rateLimits": {"primary": None, "secondary": None}}
        models = [{"id": "gpt-6.1-sol", "displayName": None}]
        table = check_codex_quota.format_table(account, rate_limits, models)
        self.assertIn("Primary (N/A)", table)
        self.assertIn("N/A used (N/A remaining)", table)
        self.assertIn("gpt-6.1-sol", table)

    def test_format_table_target_model_with_none_display_name(self):
        account = {"planType": "plus", "email": "user@example.com"}
        rate_limits = {"rateLimits": {}}
        models = [{"id": "gpt-6.1-sol", "displayName": None}]
        table = check_codex_quota.format_table(
            account, rate_limits, models, target_model="sol"
        )
        self.assertIn("gpt-6.1-sol", table)


if __name__ == "__main__":
    unittest.main()

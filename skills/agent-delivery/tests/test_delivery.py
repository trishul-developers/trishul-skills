import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DELIVERY_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "delivery.py"


def run_delivery(args, repo_dir: Path, models_path: Path | None = None):
    env = os.environ.copy()
    if models_path is not None:
        env["AGENT_DELIVERY_MODELS"] = str(models_path)
    else:
        env.pop("AGENT_DELIVERY_MODELS", None)
    return subprocess.run(
        [sys.executable, str(DELIVERY_SCRIPT), "-C", str(repo_dir), *args],
        capture_output=True,
        text=True,
        env=env,
    )


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.models_path = self.root / "user" / "models.json"
        self.profile_path = self.repo / ".agent-delivery.json"
        self.profile = {
            "project": "demo",
            "base_branch": "main",
            "run_dir": ".local/delivery",
            "governing_docs": ["AGENTS.md"],
            "rules": ["Tests first"],
            "roles": {
                "implementor": {
                    "primary": {"provider": "claude-native", "model": "claude-sonnet-5-5", "effort": "high"},
                    "fallbacks": [{"provider": "codex", "model": "gpt-6.1-terra", "effort": "high", "sandbox": "workspace-write"}],
                },
                "reviewer": {
                    "cross_provider": True,
                    "primary": {"provider": "claude-native", "model": "claude-opus-5-5", "effort": "high"},
                    "fallbacks": [{"provider": "codex", "model": "gpt-6.2-sol", "effort": "high", "sandbox": "read-only"}],
                },
            },
        }
        self.profile_path.write_text(json.dumps(self.profile), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def read_runlog(self):
        log_file = self.repo / ".local" / "delivery" / "runlog.jsonl"
        if not log_file.is_file():
            return []
        return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_config_resolution_layering(self):
        # Project profile alone
        res = run_delivery(["pick", "implementor"], self.repo, self.models_path)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout)["model"], "claude-sonnet-5-5")

        # User default overrides project profile; user project overrides user default
        self.models_path.parent.mkdir(parents=True, exist_ok=True)
        self.models_path.write_text(
            json.dumps({
                "default": {
                    "roles": {
                        "implementor": {
                            "primary": {"provider": "agy", "model": "gemini-4-argon-high", "effort": "high"},
                            "fallbacks": [],
                        }
                    }
                },
                "projects": {
                    "demo": {
                        "roles": {
                            "implementor": {
                                "primary": {"provider": "codex", "model": "gpt-6.2-sol", "effort": "medium"},
                                "fallbacks": [],
                            }
                        }
                    }
                },
            }),
            encoding="utf-8",
        )
        res = run_delivery(["pick", "implementor"], self.repo, self.models_path)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["provider"], "codex")
        self.assertEqual(data["model"], "gpt-6.2-sol")

    def test_cross_provider_pick_skips_same_family(self):
        res = run_delivery(["pick", "reviewer", "--implemented-by", "claude"], self.repo, self.models_path)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["provider"], "codex")
        self.assertEqual(data["model"], "gpt-6.2-sol")
        self.assertEqual(data["slot"], "fallback1")

    def test_models_set_writes_user_config_and_logs(self):
        res = run_delivery(
            ["models", "set", "implementor", "--primary", "codex:gpt-6.2-sol:high:workspace-write"],
            self.repo,
            self.models_path,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        saved = json.loads(self.models_path.read_text(encoding="utf-8"))
        slot = saved["projects"]["demo"]["roles"]["implementor"]["primary"]
        self.assertEqual(slot, {"provider": "codex", "model": "gpt-6.2-sol", "effort": "high", "sandbox": "workspace-write"})
        events = self.read_runlog()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "models-set")

    def test_brief_writes_meta_and_run_picks_it_up(self):
        tpl = self.root / "tpl.md"
        tpl.write_text("Step {{step}} in {{worktree}} on {{branch}} at {{head}} round {{round}}\nRules:\n{{rules}}", encoding="utf-8")
        wt = self.root / "wt-1"
        wt.mkdir()
        brief_out = self.root / "brief.md"

        res = run_delivery(
            [
                "brief", str(tpl),
                "--set", "step=S01.02",
                "--set", f"worktree={wt}",
                "--set", "branch=feat/s01",
                "--set", "head=abc1234",
                "--set", "round=2",
                "--out", str(brief_out),
            ],
            self.repo,
            self.models_path,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        meta_file = brief_out.with_name("brief.md.meta.json")
        self.assertTrue(meta_file.is_file())
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        self.assertEqual(meta, {"step": "S01.02", "worktree": str(wt), "branch": "feat/s01", "head": "abc1234", "round": "2"})

        # --dry-run does not log
        dry = run_delivery(["run", "implementor", "--brief", str(brief_out), "--dry-run"], self.repo, self.models_path)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        dry_out = json.loads(dry.stdout)
        self.assertTrue(dry_out["dry_run"])
        self.assertEqual(dry_out["cwd"], str(wt))
        self.assertEqual(self.read_runlog(), [])

        # Real native run logs dispatch with step, cwd, round from meta
        real = run_delivery(["run", "implementor", "--brief", str(brief_out)], self.repo, self.models_path)
        self.assertEqual(real.returncode, 0, real.stderr)
        events = self.read_runlog()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "dispatch")
        self.assertEqual(events[0]["step"], "S01.02")
        self.assertEqual(events[0]["cwd"], str(wt))
        self.assertEqual(events[0]["round"], "2")

    def test_agy_wsl_provider_family_and_command(self):
        self.profile["roles"]["reviewer"]["fallbacks"] = [
            {"provider": "agy-wsl", "model": "gemini-4-hydrogen-high", "effort": "high"}]
        self.profile_path.write_text(json.dumps(self.profile), encoding="utf-8")
        pick = run_delivery(["pick", "reviewer", "--implemented-by", "claude"], self.repo, self.models_path)
        self.assertEqual(pick.returncode, 0, pick.stderr)
        self.assertEqual(json.loads(pick.stdout)["provider"], "agy-wsl")
        # a Gemini model on agy-wsl is the gemini family, so it is not independent of a gemini implementor
        same = run_delivery(["pick", "reviewer", "--implemented-by", "gemini"], self.repo, self.models_path)
        self.assertEqual(same.returncode, 0, same.stderr)
        self.assertNotEqual(json.loads(same.stdout)["provider"], "agy-wsl")

        brief = self.root / "brief.md"
        brief.write_text("hello", encoding="utf-8")
        res = run_delivery(["run", "reviewer", "--brief", str(brief), "--fallback", "--cwd", str(self.root),
                            "--auto-approve", "--dry-run"], self.repo, self.models_path)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("agy_wsl_headless.py", res.stderr)
        for token in ("gemini-4-hydrogen-high", "--output-format json", "--auto-approve", "--dry-run"):
            self.assertIn(token, res.stderr)
        # --auto-approve stays refused for other providers
        bad = run_delivery(["run", "implementor", "--brief", str(brief), "--fallback", "--auto-approve", "--dry-run"],
                           self.repo, self.models_path)
        self.assertNotEqual(bad.returncode, 0)

    def test_done_followup_and_status(self):
        res1 = run_delivery(
            [
                "done", "implementor",
                "--step", "S01.02",
                "--status", "ok",
                "--round", "1",
                "--tokens", "1200",
                "--minutes", "3",
                "--sha", "deadbeef",
                "--note", "initial pass",
            ],
            self.repo,
            self.models_path,
        )
        self.assertEqual(res1.returncode, 0, res1.stderr)

        res2 = run_delivery(
            [
                "done", "implementor",
                "--step", "S01.02",
                "--status", "ok",
                "--followup",
                "--tokens", "450",
            ],
            self.repo,
            self.models_path,
        )
        self.assertEqual(res2.returncode, 0, res2.stderr)

        events = self.read_runlog()
        self.assertEqual(len(events), 2)
        self.assertNotIn("followup", events[0])
        self.assertTrue(events[1]["followup"])
        self.assertEqual(events[1]["tokens"], 450)

        st = run_delivery(["status"], self.repo, self.models_path)
        self.assertEqual(st.returncode, 0, st.stderr)
        self.assertIn("S01.02: complete implementor ok", st.stdout)


if __name__ == "__main__":
    unittest.main()

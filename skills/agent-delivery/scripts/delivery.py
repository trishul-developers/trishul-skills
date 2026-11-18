#!/usr/bin/env python3
"""agent-delivery: role table, brief rendering, headless dispatch and a run log.

One driver session plans and judges; workers do the work. Workers are either
native subagents of the driver (provider "claude-native") or headless runs of
Codex, Antigravity or Claude, started through the sibling *-headless skills.

Subcommands:
  roles   print the role table of a profile
  pick    print the provider slot a role resolves to (JSON)
  brief   render a brief template into the run directory
  run     dispatch a role with a brief; headless providers run now, native ones
          print the slot for the driver to start with its own subagent tool
  log     append an event (verdict, merge, decision, ...) to the run log
  status  show the latest run-log events, and the latest event per step

Python 3 standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILLS_ROOT = SKILL_DIR.parent
RUNNERS = {
    "codex": ("codex-headless", "codex_headless.py"),
    "agy": ("agy-headless", "agy_headless.py"),
    "claude-headless": ("claude-headless", "claude_headless.py"),
}
PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def die(msg: str, code: int = 2) -> None:
    print(f"agent-delivery: {msg}", file=sys.stderr)
    sys.exit(code)


def user_models_path() -> Path:
    return Path(os.environ.get("AGENT_DELIVERY_MODELS") or Path.home() / ".agent-delivery" / "models.json")


def read_json(p: Path) -> dict:
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_profile(name: str | None, repo_dir: Path) -> dict:
    """Project profile (rules, docs, role definitions) with the user's model config layered on top.

    Model slots come from, in rising priority: the project profile, the user's
    "default" roles, then the user's entry for this project. The user file is
    local and never part of the project or the skill.
    """
    candidates = []
    if name:
        candidates += [Path(name), SKILL_DIR / "profiles" / f"{name}.json"]
    elif os.environ.get("AGENT_DELIVERY_PROFILE"):
        return load_profile(os.environ["AGENT_DELIVERY_PROFILE"], repo_dir)
    else:
        candidates.append(repo_dir / ".agent-delivery.json")
    prof = None
    for c in candidates:
        if c.is_file():
            prof = read_json(c)
            break
    if prof is None:
        die("no profile found: pass --profile <name|path>, set AGENT_DELIVERY_PROFILE, "
            "or add .agent-delivery.json to the repository (start from the skill's profiles/example.json)")
    prof.setdefault("roles", {})
    prof["_model_source"] = {r: "project" for r, v in prof["roles"].items() if v.get("primary")}
    up = user_models_path()
    if up.is_file():
        user = read_json(up)
        layers = [("user default", user.get("default", {}).get("roles", {})),
                  ("user project", user.get("projects", {}).get(prof.get("project", ""), {}).get("roles", {}))]
        for label, roles in layers:
            for rname, slots in roles.items():
                role = prof["roles"].setdefault(rname, {})
                for k in ("primary", "fallbacks"):
                    if k in slots:
                        role[k] = slots[k]
                        role.pop("secondary", None)
                prof["_model_source"][rname] = label
    if not prof["roles"]:
        die("no roles defined in the project profile or the user model config")
    return prof


def parse_slot(text: str) -> dict:
    """provider:model:effort[:sandbox-or-mode]"""
    parts = text.split(":")
    if len(parts) < 2:
        die(f"slot '{text}' must be provider:model[:effort[:sandbox|mode]]")
    slot = {"provider": parts[0], "model": parts[1]}
    if len(parts) > 2 and parts[2]:
        slot["effort"] = parts[2]
    if len(parts) > 3 and parts[3]:
        slot["sandbox" if parts[0] == "codex" else "mode"] = parts[3]
    if slot["provider"] not in ("claude-native", "claude-headless", "claude-advisor", "codex", "agy"):
        die(f"unknown provider '{slot['provider']}'")
    return slot


def cmd_models(a, prof, repo_dir):
    up = user_models_path()
    if a.action == "path":
        print(up)
        return
    if a.action == "show":
        print(f"user model config: {up} ({'present' if up.is_file() else 'absent'})")
        fmt = lambda x: f"{x.get('provider')}:{x.get('model')}/{x.get('effort', '-')}"
        for name, r in prof["roles"].items():
            print(f"- {name} [{prof['_model_source'].get(name, 'none')}]: " + "  ->  ".join(fmt(s) for _, s in chain(r)))
        return
    # set
    if not a.role or not a.primary:
        die("models set needs ROLE and --primary")
    user = read_json(up) if up.is_file() else {}
    scope = user.setdefault("default", {}) if a.all_projects else         user.setdefault("projects", {}).setdefault(prof.get("project", "default"), {})
    entry = {"primary": parse_slot(a.primary)}
    entry["fallbacks"] = [parse_slot(x) for x in (a.fallback_slot or [])]
    scope.setdefault("roles", {})[a.role] = entry
    up.parent.mkdir(parents=True, exist_ok=True)
    up.write_text(json.dumps(user, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
    append_log(prof, repo_dir, {"event": "models-set", "role": a.role,
                                "scope": "all projects" if a.all_projects else prof.get("project"),
                                "primary": a.primary, "fallbacks": a.fallback_slot or []})
    print(f"set {a.role} in {up}")


def run_dir(prof: dict, repo_dir: Path) -> Path:
    d = repo_dir / prof.get("run_dir", ".local/delivery")
    d.mkdir(parents=True, exist_ok=True)
    return d


def append_log(prof: dict, repo_dir: Path, event: dict) -> None:
    event = {"at": now(), **event}
    with open(run_dir(prof, repo_dir) / "runlog.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def family(slot: dict) -> str:
    """Model vendor family, used for independence checks (agy hosts Claude and Gemini models)."""
    prov, model = slot.get("provider", ""), (slot.get("model") or "").lower()
    if prov in ("claude-native", "claude-headless", "claude-advisor"):
        return "claude"
    if prov == "codex":
        return "codex"
    if prov == "agy":
        if model.startswith("claude"):
            return "claude"
        if model.startswith("gpt"):
            return "oss"
        return "gemini"
    return prov


def norm_family(x: str) -> str:
    x = x.lower()
    if x in ("claude", "codex", "gemini", "oss"):
        return x
    if x.startswith("claude"):
        return "claude"
    if x in ("agy", "antigravity") or x.startswith("gemini"):
        return "gemini"
    return x


def chain(r: dict) -> list[tuple[str, dict]]:
    out = [("primary", r["primary"])] if r.get("primary") else []
    fbs = r.get("fallbacks") or ([r["secondary"]] if r.get("secondary") else [])
    out += [(f"fallback{i + 1}", s) for i, s in enumerate(fbs) if s]
    return out


def resolve(prof: dict, role: str, implemented_by: str | None, fallback: int) -> tuple[dict, str]:
    roles = prof["roles"]
    if role not in roles:
        die(f"unknown role '{role}'. Known: {', '.join(roles)}")
    r = roles[role]
    slots = chain(r)
    if not slots:
        die(f"role '{role}' has no model slots; set them in the user model config (delivery.py models set {role} --primary ...)")
    if r.get("cross_provider") and implemented_by:
        fam = norm_family(implemented_by)
        other = [(n, s) for n, s in slots if family(s) != fam]
        same = [(n, s) for n, s in slots if family(s) == fam]
        if fallback < len(other):
            return other[fallback][1], other[fallback][0]
        if same:
            print(f"agent-delivery: warning: no independent slot left for '{role}'; using a fresh {fam} worker. "
                  "It must never have seen the implementation; mark the PR with the model.", file=sys.stderr)
            return same[0][1], same[0][0] + "-same-family"
        die(f"role '{role}' has no slot left at fallback level {fallback}")
    if fallback >= len(slots):
        die(f"role '{role}' has only {len(slots) - 1} fallback(s)")
    return slots[fallback][1], slots[fallback][0]


def cmd_roles(a, prof, repo_dir):
    print(f"profile: {prof.get('project', '?')}")
    fmt = lambda x: f"{x.get('provider')}:{x.get('model')}/{x.get('effort', '-')}"
    for name, r in prof["roles"].items():
        cross = " [cross-provider]" if r.get("cross_provider") else ""
        print(f"- {name}{cross}: " + "  ->  ".join(fmt(s) for _, s in chain(r)))
        if a.verbose and r.get("use"):
            print(f"    {r['use']}")


def cmd_pick(a, prof, repo_dir):
    slot, which = resolve(prof, a.role, a.implemented_by, a.fallback)
    print(json.dumps({"role": a.role, "slot": which, **slot}, indent=2))


def cmd_brief(a, prof, repo_dir):
    tpl = Path(a.template)
    if not tpl.is_file():
        tpl = SKILL_DIR / "templates" / f"{a.template}.md"
    if not tpl.is_file():
        die(f"template not found: {a.template}")
    values = {
        "repo_dir": str(repo_dir),
        "rules": "\n".join(f"- {x}" for x in prof.get("rules", [])) or "- (none)",
        "governing_docs": ", ".join(prof.get("governing_docs", [])) or "(none)",
        "base": prof.get("base_branch", "main"),
    }
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        values[k.strip()] = v
    for kv in a.set_file or []:
        k, _, p = kv.partition("=")
        values[k.strip()] = Path(p).read_text(encoding="utf-8").strip()
    text = tpl.read_text(encoding="utf-8")
    missing = sorted({m for m in PLACEHOLDER.findall(text) if m not in values})
    if missing and not a.allow_missing:
        die("brief is incomplete; set: " + ", ".join(missing))
    out_text = PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)
    out = Path(a.out) if a.out else run_dir(prof, repo_dir) / "briefs" / f"{stamp()}-{tpl.stem}-{values.get('step', values.get('phase', 'x'))}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(out_text, encoding="utf-8")
    meta = {k: values[k] for k in ("step", "worktree", "branch", "head", "round") if values.get(k)}
    if meta:
        meta_path(out).write_text(json.dumps(meta, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
    print(out)


def meta_path(brief: Path) -> Path:
    return brief.with_name(brief.name + ".meta.json")


def read_meta(brief: Path) -> dict:
    p = meta_path(brief)
    if p.is_file():
        try:
            return read_json(p)
        except json.JSONDecodeError:
            return {}
    return {}


WORKTREE_ROLES = ("implementor", "maths-implementor", "reviewer", "reviewer-light", "phase-reviewer")


def runner_path(provider: str) -> Path:
    skill, script = RUNNERS[provider]
    p = SKILLS_ROOT / skill / "scripts" / script
    if not p.is_file():
        die(f"runner for '{provider}' not found at {p}; install the {skill} skill beside agent-delivery")
    return p


def cmd_run(a, prof, repo_dir):
    slot, which = resolve(prof, a.role, a.implemented_by, a.fallback)
    provider = slot["provider"]
    brief = Path(a.brief).resolve()
    if not brief.is_file():
        die(f"brief not found: {brief}")
    meta = read_meta(brief)
    step = a.step or meta.get("step")
    cwd = a.cwd or meta.get("worktree")
    if not cwd and a.role in WORKTREE_ROLES:
        print(f"agent-delivery: warning: '{a.role}' has no --cwd and its brief names no worktree; "
              f"it will run in the main checkout {repo_dir}", file=sys.stderr)
    cwd = cwd or str(repo_dir)
    rnd = a.round or meta.get("round")
    base_event = {"event": "dispatch", "role": a.role, "slot": which, "provider": provider,
                  "model": slot.get("model"), "effort": slot.get("effort"), "family": family(slot), "step": step,
                  "brief": str(brief), "cwd": cwd}
    if rnd:
        base_event["round"] = str(rnd)
    log = (lambda ev: None) if a.dry_run else (lambda ev: append_log(prof, repo_dir, ev))

    if provider == "claude-native" and not a.headless:
        log({**base_event, "status": "native"})
        done_cmd = (f"delivery.py -C \"{repo_dir}\" done {a.role} --step {step or '<step>'} --status ok|failed "
                    f"--tokens <n> --minutes <n> --report <path>" + (f" --round {rnd}" if rnd else ""))
        print(json.dumps({"dispatch": "native", "dry_run": bool(a.dry_run), "role": a.role, "model": slot.get("model"),
                          "effort": slot.get("effort"), "brief": str(brief), "cwd": cwd,
                          "instruction": "Start a fresh subagent on this model with the brief file's full text as its prompt, "
                                         "working in cwd. Never reuse an implementor's context for a review. "
                                         "When it returns, log it with the done command.",
                          "done": done_cmd}, indent=2))
        return 0
    if provider == "claude-advisor" and not a.headless:
        log({**base_event, "status": "native"})
        print(json.dumps({"dispatch": "advisor", "brief": str(brief),
                          "instruction": "If your agent has a built-in advisor tool, call it after putting the brief's "
                                         "question in context. Otherwise rerun with --headless."}, indent=2))
        return 0

    if provider == "claude-advisor" and slot.get("model") in (None, "", "builtin"):
        die("advisor slot is 'builtin' (the agent's own advisor tool); name a stronger model in the profile "
            "to run it headless, or use --fallback")
    if provider in ("claude-native", "claude-advisor"):
        provider = "claude-headless"
    out_dir = run_dir(prof, repo_dir) / "runs" / f"{stamp()}-{a.role}"
    cmd = [sys.executable, str(runner_path(provider)), "--prompt-file", str(brief), "--out-dir", str(out_dir)]
    if slot.get("model"):
        cmd += ["-m", slot["model"]]
    cmd += ["-C", cwd]
    if provider == "codex":
        cmd += ["-e", slot.get("effort", "high"), "-s", slot.get("sandbox", "read-only")]
        if a.resume:
            cmd += ["--resume", a.resume]
    elif provider == "agy":
        cmd += ["-e", slot.get("effort", "medium")]
        if slot.get("mode"):
            cmd += ["--mode", slot["mode"]]
        if a.resume:
            cmd += ["--resume", a.resume]
    elif provider == "claude-headless":
        if a.resume:
            cmd += ["--resume", a.resume]
    cmd += ["--timeout", str(a.timeout)]
    if a.dry_run:
        cmd.append("--dry-run")

    print("running: " + " ".join(f'"{c}"' if " " in c else c for c in cmd), file=sys.stderr)
    proc = subprocess.run(cmd)
    result = {}
    rf = out_dir / "result.json"
    if rf.is_file():
        try:
            result = json.loads(rf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result = {}
    thread = result.get("thread_id") or result.get("session_id") or result.get("conversation_id")
    ev = {**base_event, "provider": provider, "status": result.get("status") or ("ok" if proc.returncode == 0 else "failed"),
          "exit_code": proc.returncode, "thread": thread, "usage": result.get("usage"), "run_dir": str(out_dir)}
    if a.resume:
        ev["resume"] = "same-thread" if thread == a.resume else f"requested {a.resume}"
    log(ev)
    summary = {"dry_run": bool(a.dry_run), "exit_code": proc.returncode, "thread": thread, "run_dir": str(out_dir),
               "last_message": str(out_dir / "last_message.md"), "usage": result.get("usage")}
    print(json.dumps(summary, indent=2))
    return proc.returncode


def cmd_log(a, prof, repo_dir):
    ev = {"event": a.event}
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        ev[k.strip()] = v
    append_log(prof, repo_dir, ev)
    print("logged")


def cmd_done(a, prof, repo_dir):
    """Completion of a native (subagent) job, which delivery.py cannot observe itself."""
    ev = {"event": "complete", "role": a.role, "step": a.step, "status": a.status}
    if a.followup:
        ev["followup"] = True  # a SendMessage continuation of an earlier subagent; its tokens add to that job
    for k in ("round", "tokens", "minutes", "report", "sha", "note"):
        v = getattr(a, k)
        if v not in (None, ""):
            ev[k] = v
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        ev[k.strip()] = v
    append_log(prof, repo_dir, ev)
    print("logged")


def cmd_status(a, prof, repo_dir):
    f = run_dir(prof, repo_dir) / "runlog.jsonl"
    if not f.is_file():
        print("run log is empty")
        return
    events = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"run log: {f} ({len(events)} events)")
    per_step = {}
    for e in events:
        if e.get("step"):
            per_step[e["step"]] = e
    if per_step:
        print("latest per step:")
        for s, e in per_step.items():
            print(f"  {s}: {e.get('event')} {e.get('role', '')} {e.get('status', e.get('verdict', ''))} {e.get('at')}")
    print(f"last {a.n}:")
    for e in events[-a.n:]:
        keys = ("event", "role", "step", "provider", "model", "status", "verdict", "pr", "sha", "thread", "note")
        print("  " + e.get("at", "") + " " + " ".join(f"{k}={e[k]}" for k in keys if e.get(k)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", help="profile name (in profiles/) or path")
    ap.add_argument("-C", "--repo-dir", default=".", help="repository root (run log lives under it)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("roles"); p.add_argument("-v", "--verbose", action="store_true")
    p = sub.add_parser("pick"); p.add_argument("role"); p.add_argument("--implemented-by", help="family or provider of the implementor: claude, codex, gemini, agy"); p.add_argument("--fallback", action="count", default=0, help="repeat to go further down the chain")
    p = sub.add_parser("brief"); p.add_argument("template")
    p.add_argument("--set", action="append", metavar="KEY=VALUE")
    p.add_argument("--set-file", action="append", metavar="KEY=PATH")
    p.add_argument("--out"); p.add_argument("--allow-missing", action="store_true")
    p = sub.add_parser("run"); p.add_argument("role"); p.add_argument("--brief", required=True)
    p.add_argument("--step"); p.add_argument("--implemented-by", help="family or provider of the implementor: claude, codex, gemini, agy"); p.add_argument("--fallback", action="count", default=0, help="repeat to go further down the chain")
    p.add_argument("--cwd", help="worktree to run in (default: repo dir)")
    p.add_argument("--resume", metavar="THREAD_ID"); p.add_argument("--timeout", type=int, default=3600)
    p.add_argument("--headless", action="store_true", help="run claude-native roles through claude -p")
    p.add_argument("--round", help="fix/recheck round number (default: from the brief)")
    p.add_argument("--dry-run", action="store_true", help="check the command; nothing is logged")
    p = sub.add_parser("done", help="log the completion of a native subagent job")
    p.add_argument("role"); p.add_argument("--step", required=True)
    p.add_argument("--status", required=True, choices=["ok", "failed", "stopped"])
    p.add_argument("--round"); p.add_argument("--tokens", type=int); p.add_argument("--minutes", type=int)
    p.add_argument("--report"); p.add_argument("--sha"); p.add_argument("--note")
    p.add_argument("--followup", action="store_true", help="this was a SendMessage follow-up to a subagent already logged")
    p.add_argument("--set", action="append", metavar="KEY=VALUE")
    p = sub.add_parser("log"); p.add_argument("event"); p.add_argument("--set", action="append", metavar="KEY=VALUE")
    p = sub.add_parser("status"); p.add_argument("-n", type=int, default=15)
    p = sub.add_parser("models", help="show or change the user's local model config")
    p.add_argument("action", choices=["show", "set", "path"])
    p.add_argument("role", nargs="?")
    p.add_argument("--primary", metavar="provider:model[:effort[:sandbox|mode]]")
    p.add_argument("--fallback-slot", action="append", metavar="provider:model[:effort[:sandbox|mode]]",
                   help="repeat, in order")
    p.add_argument("--all-projects", action="store_true", help="write to the user default instead of this project")

    a = ap.parse_args()
    repo_dir = Path(a.repo_dir).resolve()
    prof = load_profile(a.profile, repo_dir)
    fn = {"roles": cmd_roles, "pick": cmd_pick, "brief": cmd_brief, "run": cmd_run, "log": cmd_log, "done": cmd_done, "status": cmd_status, "models": cmd_models}[a.cmd]
    return fn(a, prof, repo_dir) or 0


if __name__ == "__main__":
    sys.exit(main())

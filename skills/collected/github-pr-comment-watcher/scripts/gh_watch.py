#!/usr/bin/env python3
"""Poll structured GitHub PR handoffs without automatically consuming them."""
import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from gh_helper import comments

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROLES = ("COORDINATOR", "IMPLEMENTOR-1", "IMPLEMENTOR-LOCAL", "REVIEWER-1A", "REVIEWER-1B")
HEADER = re.compile(r"^\[(COORDINATOR|IMPLEMENTOR-1|IMPLEMENTOR-LOCAL|REVIEWER-1A|REVIEWER-1B)\](?:\s|$)")
FIELD = re.compile(r"^([A-Z][A-Z0-9_]*):\s*(.*?)\s*$", re.MULTILINE)
SHA = re.compile(r"\b[0-9a-fA-F]{40}\b")


def parse(body, role):
    head = HEADER.match(body.lstrip("\ufeff"))
    if not head:
        return None
    fields = {k: v.strip().strip("`") for k, v in FIELD.findall(body)}
    targets = set()
    for key in ("ASSIGNED_TO", "NEXT_OWNER"):
        targets.update(re.findall(r"\b(?:COORDINATOR|IMPLEMENTOR-1|IMPLEMENTOR-LOCAL|REVIEWER-1A|REVIEWER-1B)\b", fields.get(key, "")))
    if role not in targets:
        return None
    commit = next((fields[k] for k in ("START_SHA", "CANDIDATE_SHA", "FINAL_SHA", "COMMIT_SHA", "SHA") if SHA.fullmatch(fields.get(k, ""))), None)
    return {"source_role": head.group(1), "fields": fields, "handoff_id": fields.get("HANDOFF") or fields.get("HANDOFF_ID") or "UNSPECIFIED", "commit_sha": commit}


def load(path):
    if not path.exists():
        return {"version": 1, "consumed": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("consumed"), dict):
        raise ValueError("Invalid state file: consumed must be an object")
    return data


def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".pr_watch_", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            json.dump(state, out, ensure_ascii=False, indent=2, sort_keys=True)
            out.write("\n")
            out.flush(); os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def key(a, comment_id):
    return f"{a.repo}#{a.pr}:{a.role}:{comment_id}"


def check(a, state):
    for row in comments(a.repo, a.pr):
        parsed = parse(row.get("body") or "", a.role)
        if not parsed or key(a, row["id"]) in state["consumed"]:
            continue
        fields = parsed["fields"]
        print(f"HANDOFF_ID: {parsed['handoff_id']}")
        print(f"COMMENT_ID: {row['id']}")
        print(f"AUTHOR: {row.get('user',{}).get('login','unknown')}")
        print(f"TIMESTAMP: {row.get('created_at','')}")
        print(f"COMMIT_SHA: {parsed['commit_sha'] or 'UNSPECIFIED'}")
        print(f"SOURCE_ROLE: {parsed['source_role']}")
        print(f"NEXT_REQUIRED_ROLE_ACTION: {a.role} — {fields.get('REQUIRED_ACTION') or fields.get('STATE') or 'Review the directive block and act within its stated scope'}")
        print("DIRECTIVE_BLOCK_BEGIN")
        print(row.get("body", ""))
        print("DIRECTIVE_BLOCK_END")
        return True
    print("NO_NEW_HANDOFF")
    return False


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)
    for action in ("check", "watch", "mark-consumed", "status"):
        q = sub.add_parser(action)
        q.add_argument("--repo", required=True); q.add_argument("--pr", type=int, required=True)
        q.add_argument("--role", choices=ROLES, required=True)
        q.add_argument("--repo-dir", type=Path, default=Path.cwd())
        q.add_argument("--state-file", type=Path)
        if action == "watch":
            q.add_argument("--interval", type=float, default=30)
            q.add_argument("--timeout", type=float, default=300)
        if action == "mark-consumed":
            q.add_argument("--comment-id", type=int, required=True)
    a = p.parse_args()
    a.state_file = a.state_file or a.repo_dir / ".agents" / "state" / "pr_watch_state.json"
    state = load(a.state_file)
    if a.action == "mark-consumed":
        matches = [r for r in comments(a.repo, a.pr) if r["id"] == a.comment_id and parse(r.get("body") or "", a.role)]
        if not matches:
            raise ValueError("Comment ID is absent or not assigned to this role")
        row = matches[0]
        state["consumed"][key(a, a.comment_id)] = {"created_at": row.get("created_at"), "consumed_at": datetime.now(timezone.utc).isoformat()}
        save(a.state_file, state)
        print(f"CONSUMED: {a.comment_id}")
    elif a.action == "status":
        print(json.dumps({k: v for k, v in state["consumed"].items() if k.startswith(f"{a.repo}#{a.pr}:{a.role}:")}, ensure_ascii=False, indent=2))
    elif a.action == "check":
        check(a, state)
    else:
        if a.interval <= 0 or a.timeout < 0:
            raise ValueError("interval must be positive and timeout nonnegative")
        deadline = time.monotonic() + a.timeout
        while True:
            if check(a, load(a.state_file)) or time.monotonic() >= deadline:
                break
            time.sleep(min(a.interval, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
"""
GitHub PR Watcher and Role Assignment Detector.
Ukrainian Warfare Project.

Monitors PR #28 for incoming [COORDINATOR] role assignments to IMPLEMENTOR-1,
verifies START_SHA against local git HEAD, and tracks consumed handoff IDs to
prevent duplicate execution loops.
"""

import argparse
import json
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_PR = 28
DEFAULT_BRANCH = "fix/issue-26-phases-05-09-remediation"
DEFAULT_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..",
    "state",
    "pr_watch_state.json",
)


def run_cmd(cmd, cwd=None):
    res = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def load_state(state_file):
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "pr": DEFAULT_PR,
        "consumed_handoffs": [],
        "last_seen_comment_id": None,
        "last_processed_sha": None,
    }


def save_state(state_file, state):
    os.makedirs(os.path.dirname(os.path.abspath(state_file)), exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def fetch_pr_data(pr_number):
    # Try gh.exe first
    gh_paths = ["gh", r"C:\Program Files\GitHub CLI\gh.exe"]
    gh_bin = None
    for p in gh_paths:
        code, out, _ = run_cmd([p, "--version"])
        if code == 0:
            gh_bin = p
            break

    if gh_bin:
        code, out, err = run_cmd([gh_bin, "pr", "view", str(pr_number), "--json", "comments,headRefOid,headRefName,state"])
        if code == 0 and out:
            try:
                return json.loads(out)
            except Exception:
                pass

    # Fallback: gh_helper.py
    helper = os.path.join(os.path.dirname(__file__), "gh_helper.py")
    if os.path.exists(helper):
        code, out, _ = run_cmd([sys.executable, helper, "comments", "list", "--pr", str(pr_number), "--limit", "100"])
        # If helper succeeds, we can query via python urllib
    print("ERROR: Failed to fetch PR data from GitHub CLI or API.", file=sys.stderr)
    return None


def parse_coordinator_comment(body):
    if "[COORDINATOR]" not in body:
        return None

    assigned_match = re.search(r"ASSIGNED_TO:\s*([^\r\n]+)", body)
    if not assigned_match:
        return None
    assigned_to = assigned_match.group(1).strip()

    handoff_match = re.search(r"HANDOFF:\s*([^\r\n]+)", body)
    handoff_id = handoff_match.group(1).strip() if handoff_match else "UNKNOWN"

    state_match = re.search(r"STATE:\s*([^\r\n]+)", body)
    state = state_match.group(1).strip() if state_match else "UNKNOWN"

    branch_match = re.search(r"BRANCH:\s*`?([^`\r\n]+)`?", body)
    branch = branch_match.group(1).strip() if branch_match else DEFAULT_BRANCH

    start_sha_match = re.search(r"START_SHA:\s*`?([0-9a-fA-F]{40})`?", body)
    start_sha = start_sha_match.group(1).strip() if start_sha_match else None

    # Scope / instructions
    scope_match = re.search(r"REQUIRED_REMEDIATION:(.*?)(?=EVIDENCE_POLICY:|FINAL_HANDOFF_REQUIREMENTS:|EXCLUSIONS:|$)", body, re.DOTALL)
    scope = scope_match.group(1).strip() if scope_match else ""

    return {
        "handoff_id": handoff_id,
        "assigned_to": assigned_to,
        "state": state,
        "branch": branch,
        "start_sha": start_sha,
        "scope": scope,
    }


def cmd_check(args):
    state_file = os.path.abspath(args.state_file)
    state = load_state(state_file)
    pr_data = fetch_pr_data(args.pr)
    if not pr_data:
        sys.exit(1)

    comments = pr_data.get("comments", [])
    head_sha = pr_data.get("headRefOid", "")
    head_ref = pr_data.get("headRefName", "")

    # Iterate from latest to oldest
    target_assignment = None
    target_cid = None
    target_role_norm = args.role.replace("_", "-").upper()
    for c in reversed(comments):
        parsed = parse_coordinator_comment(c.get("body", ""))
        if parsed:
            assigned_norm = parsed["assigned_to"].replace("_", "-").upper()
            if assigned_norm == target_role_norm:
                target_assignment = parsed
                target_cid = c.get("id")
                break

    if not target_assignment:
        print(f"IDLE: No [{args.role}] assignment found on PR #{args.pr}.")
        return

    handoff_id = target_assignment["handoff_id"]
    if handoff_id in state.get("consumed_handoffs", []):
        print(f"IDLE: Latest assignment '{handoff_id}' has already been consumed.")
        return

    print("=======================================================")
    print(f"       NEW UNCONSUMED [{args.role}] ASSIGNMENT FOUND     ")
    print("=======================================================")
    print(f"PR Number    : #{args.pr} ({head_ref})")
    print(f"Remote HEAD  : {head_sha}")
    print(f"Comment ID   : {target_cid}")
    print(f"Handoff ID   : {handoff_id}")
    print(f"State        : {target_assignment['state']}")
    print(f"Branch       : {target_assignment['branch']}")
    print(f"START_SHA    : {target_assignment['start_sha']}")
    print("-------------------------------------------------------")
    print("Remediation Scope:")
    for line in target_assignment["scope"].splitlines()[:15]:
        print(f"  {line}")
    if len(target_assignment["scope"].splitlines()) > 15:
        print("  ...")
    print("-------------------------------------------------------")

    # Local git validation
    _, local_branch, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    _, local_head, _ = run_cmd(["git", "rev-parse", "HEAD"])
    code, status_out, _ = run_cmd(["git", "status", "--porcelain"])

    print("Local Git Validation:")
    print(f"  Current Branch : {local_branch} (Expected: {target_assignment['branch']})")
    print(f"  Current HEAD   : {local_head} (Expected: {target_assignment['start_sha']})")
    print(f"  Working Tree   : {'DIRTY' if status_out else 'CLEAN'}")

    is_ready = True
    if target_assignment["start_sha"] and local_head != target_assignment["start_sha"]:
        print(f"\n[BLOCKED] Local HEAD ({local_head}) does not match START_SHA ({target_assignment['start_sha']}).", file=sys.stderr)
        is_ready = False

    if local_branch != target_assignment["branch"]:
        print(f"\n[BLOCKED] Local branch ({local_branch}) does not match assigned branch ({target_assignment['branch']}).", file=sys.stderr)
        is_ready = False

    if is_ready:
        print("\nSTATUS: READY_FOR_IMPLEMENTATION")
        if args.auto_consume:
            state["consumed_handoffs"].append(handoff_id)
            state["last_seen_comment_id"] = target_cid
            state["last_processed_sha"] = target_assignment["start_sha"]
            save_state(state_file, state)
            print(f"Recorded '{handoff_id}' in consumed ledger.")
    else:
        print("\nSTATUS: BLOCKED_PRECONDITION_FAILED")
        sys.exit(1)


def cmd_mark_consumed(args):
    state_file = os.path.abspath(args.state_file)
    state = load_state(state_file)
    if args.handoff_id not in state["consumed_handoffs"]:
        state["consumed_handoffs"].append(args.handoff_id)
        save_state(state_file, state)
        print(f"SUCCESS: Marked '{args.handoff_id}' as consumed in {state_file}")
    else:
        print(f"Handoff '{args.handoff_id}' was already in consumed list.")


def cmd_status(args):
    state_file = os.path.abspath(args.state_file)
    state = load_state(state_file)
    print(f"State file: {state_file}")
    print(f"PR: {state.get('pr')}")
    print(f"Consumed handoffs: {state.get('consumed_handoffs', [])}")
    print(f"Last processed SHA: {state.get('last_processed_sha')}")


def main():
    parser = argparse.ArgumentParser(description="PR Watcher and Role Assignment Detector")
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE, help="Path to state tracking JSON file")
    parser.add_argument("--pr", type=int, default=DEFAULT_PR, help=f"PR number (default: {DEFAULT_PR})")
    parser.add_argument("--role", default="IMPLEMENTOR-LOCAL", help="Target role tag to watch for (default: IMPLEMENTOR-LOCAL)")

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # check
    p_check = subparsers.add_parser("check", help="Check for new unconsumed assignments")
    p_check.add_argument("--auto-consume", action="store_true", help="Automatically mark handoff as consumed")
    p_check.set_defaults(func=cmd_check)

    # mark-consumed
    p_mark = subparsers.add_parser("mark-consumed", help="Mark a handoff ID as consumed")
    p_mark.add_argument("handoff_id", help="Handoff ID to mark as consumed (e.g. ISSUE26-020)")
    p_mark.set_defaults(func=cmd_mark_consumed)

    # status
    p_status = subparsers.add_parser("status", help="Show current watcher state")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

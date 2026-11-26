#!/usr/bin/env python3
"""
GitHub PR Watcher and Role Assignment Detector.

Monitors a PR for incoming [COORDINATOR] role assignments, verifies START_SHA
against local git HEAD, and tracks consumed handoff IDs to prevent duplicate
execution loops.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def default_state_file():
    code, out, _ = run_cmd(["git", "rev-parse", "--show-toplevel"])
    if code == 0 and out:
        return os.path.join(out, ".local", "pr_watch_state.json")
    return os.path.join(tempfile.gettempdir(), "pr_watch_state.json")


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
        "pr": None,
        "consumed_handoffs": [],
        "last_seen_comment_id": None,
        "last_processed_sha": None,
    }


def save_state(state_file, state):
    os.makedirs(os.path.dirname(os.path.abspath(state_file)), exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def fetch_pr_data(pr_number, repo=None):
    # Try gh CLI first
    gh_bin = shutil.which("gh")
    if not gh_bin and os.name == "nt":
        win_gh = r"C:\Program Files\GitHub CLI\gh.exe"
        if os.path.exists(win_gh):
            gh_bin = win_gh

    if gh_bin:
        cmd = [gh_bin, "pr", "view", str(pr_number), "--json", "comments,headRefOid,headRefName,state"]
        if repo:
            cmd.extend(["--repo", repo])
        code, out, err = run_cmd(cmd)
        if code == 0 and out:
            try:
                return json.loads(out)
            except Exception:
                pass

    # Fallback: GitHub REST API via gh_helper
    try:
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import gh_helper

        target_repo = gh_helper.get_repo(repo)
        pr_info = gh_helper.api_request(f"/repos/{target_repo}/pulls/{pr_number}")
        comments = gh_helper.api_request(f"/repos/{target_repo}/issues/{pr_number}/comments?per_page=100")
        return {
            "comments": comments if isinstance(comments, list) else [],
            "headRefOid": (pr_info.get("head") or {}).get("sha", ""),
            "headRefName": (pr_info.get("head") or {}).get("ref", ""),
            "state": pr_info.get("state", ""),
        }
    except SystemExit:
        pass
    except Exception as e:
        print(f"ERROR: Fallback API fetch failed: {e}", file=sys.stderr)
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
    branch = branch_match.group(1).strip() if branch_match else None

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
    if not args.pr:
        print("ERROR: --pr is required for check.", file=sys.stderr)
        sys.exit(2)
    state_file = os.path.abspath(args.state_file or default_state_file())
    state = load_state(state_file)
    pr_data = fetch_pr_data(args.pr, repo=args.repo)
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

    expected_branch = target_assignment["branch"] or head_ref
    print("Local Git Validation:")
    print(f"  Current Branch : {local_branch} (Expected: {expected_branch or 'N/A'})")
    print(f"  Current HEAD   : {local_head} (Expected: {target_assignment['start_sha']})")
    print(f"  Working Tree   : {'DIRTY' if status_out else 'CLEAN'}")

    is_ready = True
    if target_assignment["start_sha"] and local_head.lower() != target_assignment["start_sha"].lower():
        print(f"\n[BLOCKED] Local HEAD ({local_head}) does not match START_SHA ({target_assignment['start_sha']}).", file=sys.stderr)
        is_ready = False

    if expected_branch and local_branch != expected_branch:
        print(f"\n[BLOCKED] Local branch ({local_branch}) does not match assigned branch ({expected_branch}).", file=sys.stderr)
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
    state_file = os.path.abspath(args.state_file or default_state_file())
    state = load_state(state_file)
    if args.handoff_id not in state["consumed_handoffs"]:
        state["consumed_handoffs"].append(args.handoff_id)
        save_state(state_file, state)
        print(f"SUCCESS: Marked '{args.handoff_id}' as consumed in {state_file}")
    else:
        print(f"Handoff '{args.handoff_id}' was already in consumed list.")


def cmd_status(args):
    state_file = os.path.abspath(args.state_file or default_state_file())
    state = load_state(state_file)
    print(f"State file: {state_file}")
    print(f"PR: {state.get('pr')}")
    print(f"Consumed handoffs: {state.get('consumed_handoffs', [])}")
    print(f"Last processed SHA: {state.get('last_processed_sha')}")


def main():
    parser = argparse.ArgumentParser(description="PR Watcher and Role Assignment Detector")
    parser.add_argument("--state-file", default=None, help="Path to state tracking JSON file (default: <repo>/.local/pr_watch_state.json)")
    parser.add_argument("--repo", default=None, help="GitHub repository in 'owner/repo' format (defaults to origin remote)")
    parser.add_argument("--pr", type=int, default=None, help="PR number (required for check)")
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

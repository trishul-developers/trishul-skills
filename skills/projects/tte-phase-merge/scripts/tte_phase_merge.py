#!/usr/bin/env python3
r"""TTE Phase Merge Automation.

Merges a side/task branch into the active phase branch with a merge commit (--no-ff).
- Refuses if working tree is dirty.
- Refuses if merge would change ProjectSettings/** or Packages/** unless --allow-settings.
- Previews merge base and changed files before merging.
- Pushes only with --push, and polls for the triggered GitHub Actions CI run ID.
- Strictly refuses to touch 'main' and never force-pushes.

Standard library Python 3 only.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def run_cmd(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 60) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


def detect_repo(project_dir: Optional[Path] = None, repo_override: Optional[str] = None) -> str:
    if repo_override:
        return repo_override
    code, stdout, _ = run_cmd(["git", "remote", "get-url", "origin"], cwd=project_dir)
    if code == 0 and stdout:
        m = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)(?:\.git)?", stdout)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return "tosumitdhaka/trishul-tactical-engine"


def is_working_tree_clean(cwd: Optional[Path] = None) -> Tuple[bool, str]:
    code, stdout, _ = run_cmd(["git", "status", "--porcelain"], cwd=cwd)
    if code != 0:
        return False, "Failed to execute git status"
    return len(stdout.strip()) == 0, stdout.strip()


def get_current_branch(cwd: Optional[Path] = None) -> str:
    code, stdout, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    return stdout.strip() if code == 0 else ""


def compute_merge_base(branch_a: str, branch_b: str, cwd: Optional[Path] = None) -> Optional[str]:
    code, stdout, _ = run_cmd(["git", "merge-base", branch_a, branch_b], cwd=cwd)
    return stdout.strip() if code == 0 and stdout else None


def get_changed_files(base_sha: str, branch: str, cwd: Optional[Path] = None) -> List[str]:
    code, stdout, _ = run_cmd(["git", "diff", "--name-only", f"{base_sha}...{branch}"], cwd=cwd)
    if code == 0 and stdout:
        return [f.strip() for f in stdout.splitlines() if f.strip()]
    return []


def wait_for_ci_run(repo: str, phase_branch: str, target_sha: str, timeout: int = 60, cwd: Optional[Path] = None) -> Optional[Dict]:
    start = time.monotonic()
    target_sha_short = target_sha[:7]
    while time.monotonic() - start < timeout:
        code, stdout, _ = run_cmd([
            "gh", "run", "list",
            "--repo", repo,
            "--branch", phase_branch,
            "--limit", "5",
            "--json", "databaseId,headSha,status,conclusion,url",
        ], cwd=cwd)
        if code == 0 and stdout:
            try:
                runs = json.loads(stdout)
                for r in runs:
                    r_sha = r.get("headSha", "")
                    if r_sha == target_sha or r_sha.startswith(target_sha_short):
                        return r
            except Exception:
                pass
        time.sleep(3)
    return None


def execute_phase_merge(
    side_branch: str,
    phase_branch: str = "g02-presentation-orders-ux",
    allow_settings: bool = False,
    push: bool = False,
    custom_message: Optional[str] = None,
    dry_run: bool = False,
    wait_ci_timeout: int = 60,
    project_dir: Optional[Path] = None,
    repo_override: Optional[str] = None,
) -> int:
    repo = detect_repo(project_dir, repo_override)

    # 1. Prohibit main branch manipulation
    if side_branch.lower() == "main" or phase_branch.lower() == "main":
        print("ERROR: Touching, merging into, or merging from 'main' is prohibited by phase workflow rules.", file=sys.stderr)
        return 1

    if side_branch == phase_branch:
        print(f"ERROR: Side branch '{side_branch}' and phase branch '{phase_branch}' are identical.", file=sys.stderr)
        return 1

    # 2. Check clean working tree
    clean, status_lines = is_working_tree_clean(project_dir)
    if not clean:
        print("ERROR: Working tree is not clean. Commit or stash changes before merging:", file=sys.stderr)
        for sl in status_lines.splitlines()[:10]:
            print(f"  {sl}", file=sys.stderr)
        return 1

    # 3. Ensure we are on phase_branch
    curr_branch = get_current_branch(project_dir)
    if curr_branch != phase_branch:
        print(f"Current branch is '{curr_branch}'. Switching to phase branch '{phase_branch}'...")
        code, _, err = run_cmd(["git", "checkout", phase_branch], cwd=project_dir)
        if code != 0:
            print(f"ERROR: Failed to checkout phase branch '{phase_branch}': {err}", file=sys.stderr)
            return 1

    # 4. Compute merge base and changed files
    merge_base = compute_merge_base(phase_branch, side_branch, cwd=project_dir)
    if not merge_base:
        print(f"ERROR: Could not compute merge base between '{phase_branch}' and '{side_branch}'. Ensure '{side_branch}' exists.", file=sys.stderr)
        return 1

    changed_files = get_changed_files(merge_base, side_branch, cwd=project_dir)
    print(f"Merge base: {merge_base[:7]} (between '{phase_branch}' and '{side_branch}')")
    print(f"Files changed ({len(changed_files)}):")
    for f in changed_files[:15]:
        print(f"  - {f}")
    if len(changed_files) > 15:
        print(f"  ... (+{len(changed_files) - 15} more files)")

    # 5. Protected settings check
    offending = [
        f for f in changed_files
        if f.startswith("ProjectSettings/") or f.startswith("ProjectSettings\\")
        or f.startswith("Packages/") or f.startswith("Packages\\")
    ]
    if offending and not allow_settings:
        print(
            f"\nERROR: Merge touches {len(offending)} protected project settings/package files:",
            file=sys.stderr,
        )
        for f in offending:
            print(f"  - {f}", file=sys.stderr)
        print("Refusing merge. Use --allow-settings if changes were authorized by owner/architect.", file=sys.stderr)
        return 1

    if dry_run:
        print("\nDry-run mode enabled. Previews passed cleanly; no merge performed.")
        return 0

    # 6. Perform merge commit (--no-ff)
    msg = custom_message or f"Merge branch '{side_branch}' into {phase_branch}"
    print(f"\nMerging '{side_branch}' into '{phase_branch}' (--no-ff)...")
    code, stdout, stderr = run_cmd(["git", "merge", "--no-ff", "-m", msg, side_branch], cwd=project_dir)
    if code != 0:
        print(f"ERROR: Merge conflict or failure during git merge:\n{stderr or stdout}", file=sys.stderr)
        run_cmd(["git", "merge", "--abort"], cwd=project_dir)
        return code

    code, new_sha, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=project_dir)
    new_sha = new_sha.strip()
    print(f"SUCCESS: Created merge commit {new_sha[:7]} ({new_sha}) on {phase_branch}.")

    # 7. Push handling
    if push:
        print(f"Pushing '{phase_branch}' to origin...")
        code, p_stdout, p_stderr = run_cmd(["git", "push", "origin", phase_branch], cwd=project_dir)
        if code != 0:
            print(f"ERROR: git push failed:\n{p_stderr or p_stdout}", file=sys.stderr)
            return code
        print(f"Successfully pushed to origin/{phase_branch} at {new_sha[:7]}.")

        print(f"Waiting up to {wait_ci_timeout}s for GitHub Actions CI run...")
        ci_run = wait_for_ci_run(repo, phase_branch, new_sha, timeout=wait_ci_timeout, cwd=project_dir)
        if ci_run:
            print(f"CI Run Detected: Run ID #{ci_run.get('databaseId')}")
            print(f"URL: {ci_run.get('url')}")
            print(f"Status: {ci_run.get('status')} | Conclusion: {ci_run.get('conclusion') or 'pending'}")
        else:
            print(f"Notice: CI run was not detected within {wait_ci_timeout}s. Check https://github.com/{repo}/actions")
    else:
        print("Notice: Merge committed locally. Remote origin was not pushed. Pass --push to push to remote.")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Merge a task branch into the TTE phase branch with --no-ff and safety checks",
    )
    parser.add_argument("branch", help="Side/task branch name to merge into phase branch")
    parser.add_argument(
        "--phase-branch",
        default="g02-presentation-orders-ux",
        help="Target phase branch (default: g02-presentation-orders-ux)",
    )
    parser.add_argument(
        "--allow-settings",
        action="store_true",
        help="Allow modifications to ProjectSettings/** or Packages/**",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push the merge commit to origin and poll for the created CI run ID",
    )
    parser.add_argument(
        "-m", "--message",
        dest="message",
        help="Custom merge commit message",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify clean status, compute merge-base, and check file restrictions without merging",
    )
    parser.add_argument(
        "--wait-ci-timeout",
        type=int,
        default=60,
        help="Maximum seconds to wait for CI run creation after push (default: 60)",
    )
    parser.add_argument(
        "-C", "--dir",
        dest="project_dir",
        default=".",
        help="Path to project repository (default: .)",
    )
    parser.add_argument(
        "--repo",
        help="GitHub owner/repo override (defaults to origin URL)",
    )

    args = parser.parse_args()
    proj_dir = Path(args.project_dir).resolve() if args.project_dir else None

    return execute_phase_merge(
        side_branch=args.branch,
        phase_branch=args.phase_branch,
        allow_settings=args.allow_settings,
        push=args.push,
        custom_message=args.message,
        dry_run=args.dry_run,
        wait_ci_timeout=args.wait_ci_timeout,
        project_dir=proj_dir,
        repo_override=args.repo,
    )


if __name__ == "__main__":
    sys.exit(main())

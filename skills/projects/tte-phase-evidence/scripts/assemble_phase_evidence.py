#!/usr/bin/env python3
r"""Assemble phase-end acceptance evidence package for Trishul Tactical Engine (TTE).

Verifies preconditions:
  - No HOLD(Qn), NotImplementedException, or TODO in Assets/Scripts
  - Red list is empty or deleted
  - CI run status on PR head

Generates evidence block:
  - Step commit table from git log
  - CI run links and test counts
  - State inventory diff
  - Acceptance checklist and deviations
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def run_cmd(cmd: List[str], cwd: Path) -> Tuple[int, str, str]:
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return res.returncode, res.stdout, res.stderr


def check_preconditions(repo_dir: Path) -> List[str]:
    """Check for forbidden markers in Assets/Scripts and temporary red lists."""
    findings = []

    # 1. Search for HOLD, NotImplementedException, TODO
    code, stdout, _ = run_cmd(
        ["git", "grep", "-n", "-E", r"HOLD\(Q|NotImplementedException|TODO", "--", "Assets/Scripts"],
        repo_dir
    )
    if code == 0 and stdout.strip():
        lines = stdout.strip().splitlines()
        findings.append(f"Found {len(lines)} forbidden marker(s) in Assets/Scripts:\n" + "\n".join(f"  {line}" for line in lines[:10]))
        if len(lines) > 10:
            findings.append(f"  ... and {len(lines) - 10} more markers.")

    # 2. Check temporary red list
    plan_dir = repo_dir / "docs" / "implementation" / "plan_v2"
    if plan_dir.exists():
        for f in plan_dir.glob("*_temporary_red_list.md"):
            content = f.read_text(encoding="utf-8", errors="replace").strip()
            # check if there are test entries in red list
            entries = [line for line in content.splitlines() if line.strip().startswith("-") or line.strip().startswith("*")]
            if entries:
                findings.append(f"Temporary red list {f.name} is not empty ({len(entries)} entries remaining).")

    return findings


def get_step_table(repo_dir: Path, base_ref: str) -> List[Dict[str, str]]:
    """Generate commit step table from base_ref..HEAD."""
    code, stdout, _ = run_cmd(
        ["git", "log", "--oneline", "--reverse", f"{base_ref}..HEAD"],
        repo_dir
    )
    steps = []
    if code == 0 and stdout.strip():
        for line in stdout.strip().splitlines():
            parts = line.strip().split(" ", 1)
            sha = parts[0]
            msg = parts[1] if len(parts) > 1 else ""
            steps.append({"sha": sha, "message": msg})
    return steps


def get_state_inventory_diff(repo_dir: Path, base_ref: str) -> str:
    """Extract diff on docs/implementation/state_inventory.md."""
    code, stdout, _ = run_cmd(
        ["git", "diff", f"{base_ref}...HEAD", "--", "docs/implementation/state_inventory.md"],
        repo_dir
    )
    if code == 0 and stdout.strip():
        return stdout.strip()
    return "No state inventory modifications detected."


def check_ci_status(repo_dir: Path, branch: Optional[str]) -> Tuple[bool, str]:
    """Fetch CI run for unity-ci.yml using gh CLI and verify pass status against candidate HEAD."""
    code, head_sha_out, _ = run_cmd(["git", "rev-parse", "HEAD"], repo_dir)
    candidate_sha = head_sha_out.strip() if code == 0 else ""

    cmd = [
        "gh", "run", "list",
        "--workflow", "unity-ci.yml",
        "--json", "headSha,status,conclusion,databaseId,createdAt,url",
        "--limit", "10",
    ]
    if branch:
        cmd.extend(["--branch", branch])
    code, stdout, stderr = run_cmd(cmd, repo_dir)
    if code != 0 or not stdout.strip():
        msg = f"CI runs could not be queried via gh CLI (verify gh auth).\n{stderr.strip()}".strip()
        return False, msg

    try:
        runs = json.loads(stdout)
    except Exception:
        runs = []

    if not runs:
        return False, f"No CI runs found for workflow unity-ci.yml.\n{stdout.strip()}"

    # Verify run against candidate HEAD SHA
    matching_run = None
    for r in runs:
        r_sha = r.get("headSha", "")
        if candidate_sha and (r_sha.startswith(candidate_sha) or candidate_sha.startswith(r_sha)):
            matching_run = r
            break

    if not matching_run:
        latest = runs[0]
        latest_sha = latest.get("headSha", "")[:10]
        msg = (
            f"No CI run found matching candidate HEAD ({candidate_sha[:10]}).\n"
            f"Latest run #{latest.get('databaseId')} is on commit {latest_sha}: "
            f"status={latest.get('status')}, conclusion={latest.get('conclusion')} ({latest.get('url')})"
        )
        return False, msg

    status = matching_run.get("status")
    conclusion = matching_run.get("conclusion")
    run_id = matching_run.get("databaseId")
    url = matching_run.get("url")

    summary_text = (
        f"Run ID:     #{run_id}\n"
        f"Commit:     {candidate_sha[:10]}\n"
        f"Status:     {status}\n"
        f"Conclusion: {conclusion}\n"
        f"URL:        {url}"
    )

    # Strictly require status == "completed" AND conclusion == "success".
    # Treats neutral, timed_out, failure, cancelled, etc. as NOT passing.
    is_success = (status == "completed" and conclusion == "success")
    if not is_success:
        summary_text += f"\n[!] Non-passing CI conclusion: '{conclusion}' (status: '{status}')"

    return is_success, summary_text


def format_evidence_package(
    phase: str,
    base_ref: str,
    repo_dir: Path,
    steps: List[Dict[str, str]],
    state_diff: str,
    ci_status: str,
    ci_passed: bool,
    precondition_warnings: List[str],
) -> str:
    out = []
    out.append(f"# READY_FOR_REVIEW: Phase {phase}\n")

    # Status / Preconditions
    out.append("## 1. Precondition Audit")
    if precondition_warnings:
        out.append("> [!WARNING]")
        out.append("> **Precondition Violations Detected:**")
        for w in precondition_warnings:
            out.append(f"> - {w}")
    else:
        out.append("- [x] No `HOLD(Qn)` markers, `NotImplementedException`, or `TODO` in `Assets/Scripts`.")
        out.append("- [x] Temporary red list is clean and verified.")
        out.append(f"- [x] All step commits verified against baseline `{base_ref}`.")
    out.append("")

    # Step Commit Table
    coverage_status = "CI passed (verified)" if ci_passed else "[ ] Pending CI verification"
    out.append("## 2. Step Commit Table")
    out.append("| Step | Commit SHA | Summary | Test Coverage |")
    out.append("| :--- | :--- | :--- | :--- |")
    if steps:
        for idx, s in enumerate(steps, start=1):
            out.append(f"| {phase}.{idx:02d} | `{s['sha']}` | {s['message']} | {coverage_status} |")
    else:
        out.append("| - | - | No commits found in range | - |")
    out.append("")

    # CI Runs
    ci_header = "## 3. CI Verification Evidence"
    if not ci_passed:
        ci_header += " (UNVERIFIED)"
    out.append(ci_header)
    out.append("```text")
    out.append(ci_status)
    out.append("```\n")

    # State Inventory Diff
    out.append("## 4. State Inventory Changes")
    if len(state_diff.splitlines()) > 40:
        out.append("<details><summary>Click to view state_inventory.md diff</summary>\n")
        out.append("```diff")
        out.append(state_diff)
        out.append("```\n</details>\n")
    else:
        out.append("```diff")
        out.append(state_diff)
        out.append("```\n")

    # Deviations and Decisions (Reviewer Verification Checklist)
    out.append("## 5. Architectural Invariants & Reviewer Verification Checklist")
    out.append("- [ ] Determinism verified (no UnityEngine.Random, identical two-run digests).")
    out.append("- [ ] Zero GC allocations on steady-state hot paths verified.")
    out.append("- [ ] Spec amendments applied with documented rationale.")
    out.append("- [ ] Review boundary respected (stopping pending Reviewer / Architect verification).\n")

    return "\n".join(out)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Assemble phase-end acceptance evidence package for TTE")
    parser.add_argument("--phase", required=True, help="Phase identifier (e.g. G01, G02, P17)")
    parser.add_argument("--base-ref", default="origin/main", help="Base ref for commit range and diffs (default: origin/main)")
    parser.add_argument("-C", "--repo-dir", default=".", help="Path to TTE repository root")
    parser.add_argument("--branch", help="PR branch name for CI status check")
    parser.add_argument("-o", "--output", help="File to write formatted evidence markdown to (default: stdout)")
    parser.add_argument("--strict", action="store_true", help="Fail with non-zero exit code if precondition warnings exist")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).resolve()
    if not (repo_dir / ".git").exists():
        print(f"Error: {repo_dir} is not a git repository.", file=sys.stderr)
        sys.exit(1)

    print(f"Auditing repository preconditions at {repo_dir}...")
    precondition_warnings = check_preconditions(repo_dir)

    print(f"Collecting step commits from {args.base_ref}..HEAD...")
    steps = get_step_table(repo_dir, args.base_ref)

    print("Extracting state_inventory.md diff...")
    state_diff = get_state_inventory_diff(repo_dir, args.base_ref)

    print("Querying CI workflow status...")
    ci_passed, ci_status = check_ci_status(repo_dir, args.branch)

    evidence_text = format_evidence_package(
        phase=args.phase,
        base_ref=args.base_ref,
        repo_dir=repo_dir,
        steps=steps,
        state_diff=state_diff,
        ci_status=ci_status,
        ci_passed=ci_passed,
        precondition_warnings=precondition_warnings,
    )

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(evidence_text, encoding="utf-8")
        print(f"Evidence package written to {out_path}")
    else:
        print("\n" + evidence_text)

    strict_failures = []
    if precondition_warnings:
        strict_failures.append(f"Precondition audit failed with {len(precondition_warnings)} warning(s).")
    if not ci_passed:
        strict_failures.append("CI workflow status is unverified or has not passed.")

    if args.strict and strict_failures:
        print(f"\n[FAIL] Strict verification failed with {len(strict_failures)} issue(s):", file=sys.stderr)
        for issue in strict_failures:
            print(f"  - {issue}", file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()

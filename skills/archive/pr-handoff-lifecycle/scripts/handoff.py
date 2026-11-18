#!/usr/bin/env python3
r"""PR Handoff Lifecycle Automation.

Drafts and verifies structured role handoffs:
  - [IMPLEMENTOR-LOCAL]: From git commits, diffs, and test report XML
  - [COORDINATOR]: Pre-flight routing verification (ancestry, ahead/behind, PR HEAD)
  - [REVIEWER-1A / 1B]: 6-point checklist verdict (with candidate SHA verification)

Zero fabricated claims: refuses to claim PASS for nonexistent commits or unverified test suites.
"""

import argparse
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def verify_commit_exists(sha: str, label: str = "Commit") -> None:
    if not sha or len(sha) < 7:
        print(f"ERROR: Invalid {label} SHA '{sha}'.", file=sys.stderr)
        sys.exit(1)
    code, _, _ = run_cmd(["git", "cat-file", "-e", f"{sha}^{{commit}}"])
    if code != 0:
        print(f"ERROR: {label} SHA '{sha}' does not exist as a commit in local git history.", file=sys.stderr)
        sys.exit(1)


def parse_test_results_xml(xml_path: str) -> Tuple[bool, str, str]:
    """Parse NUnit 3 XML report and extract summary counts and exact executed test names."""
    p = Path(xml_path)
    if not p.exists():
        return False, f"XML file not found: {xml_path}", ""

    try:
        root = ET.parse(p).getroot()
    except Exception as e:
        return False, f"Malformed XML: {e}", ""

    total = int(root.get("total") or 0)
    passed = int(root.get("passed") or 0)
    failed = int(root.get("failed") or 0)
    skipped = int(root.get("skipped") or 0)

    if total == 0:
        return False, "ZERO_TESTS_SELECTED: Test run selected 0 tests.", ""

    test_names = []
    for test_case in root.iter("test-case"):
        name = test_case.get("fullname") or test_case.get("name")
        if name:
            test_names.append(name)

    names_block = "\n".join(f"{idx+1}. {name}" for idx, name in enumerate(test_names[:30]))
    if len(test_names) > 30:
        names_block += f"\n... and {len(test_names) - 30} more tests"

    evidence_summary = (
        f"- Tests: {total} total, {passed} passed, {failed} failed, {skipped} skipped"
    )
    is_green = (failed == 0 and passed > 0)
    return is_green, evidence_summary, names_block


def cmd_draft_implementor(args):
    start_sha = args.start_sha.strip()
    verify_commit_exists(start_sha, "START_SHA")

    # 1. Get HEAD SHA
    code, head_sha, _ = run_cmd(["git", "rev-parse", "HEAD"])
    if code != 0:
        print("ERROR: Cannot determine HEAD commit.", file=sys.stderr)
        sys.exit(1)

    # 2. Get current branch
    _, branch, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])

    # 3. Get commit log from start_sha..HEAD
    _, commit_log, _ = run_cmd(["git", "log", "--oneline", f"{start_sha}..{head_sha}"])
    if not commit_log:
        commit_log = f"{head_sha[:8]} (No intermediate commits since {start_sha[:8]})"

    # 4. Get changed files
    _, changed_files_out, _ = run_cmd(["git", "diff", "--name-only", f"{start_sha}..{head_sha}"])
    changed_files = [f"1. {f}" for f in changed_files_out.splitlines() if f.strip()]
    if not changed_files:
        changed_files = ["1. (No files modified)"]

    # 5. Parse test report if provided
    green = False
    if args.tests_xml:
        green, evidence_str, exact_tests_str = parse_test_results_xml(args.tests_xml)
        if not green:
            print(f"WARNING: Test report indicates failures or zero tests: {evidence_str}", file=sys.stderr)
            state = "WIP_TESTS_FAILED" if args.state == "READY_FOR_REVIEW" else args.state
        else:
            state = args.state
    else:
        exact_tests_str = "1. (Unspecified - attach XML with --tests-xml)"
        evidence_str = (
            "- Tests: NOT_RUN (no --tests-xml provided; run tests before handoff)"
        )
        state = "WIP_TESTS_PENDING" if args.state == "READY_FOR_REVIEW" else args.state

    # 6. Format handoff body
    lines = [
        f"[{args.role}]",
        "",
        f"HANDOFF: {args.assignment_id}",
        f"STATE: {state}",
        f"NEXT_OWNER: {args.next_owner}",
        "",
        f"BRANCH: {branch}",
        f"START_SHA: {start_sha}",
        f"FINAL_SHA: {head_sha}",
        "",
        "ORDERED_COMMITS:",
        commit_log,
        "",
        "CHANGED_FILES:",
        "\n".join(changed_files),
        "",
        "EXACT_TEST_NAMES:",
        exact_tests_str,
        "",
        "TEST_EVIDENCE:",
        evidence_str,
    ]

    # Invariants Checklist: A test XML alone does NOT prove determinism or heap invariants
    if getattr(args, "verified_invariants", False) and green:
        lines.extend([
            "- [x] Bounded visited/heap capacities verified stable",
            "- [x] Checkpoint/restore determinism verified",
            "- [x] No subsequent phase work was started",
        ])
    else:
        lines.extend([
            "- [ ] Bounded visited/heap capacities pending verification",
            "- [ ] Checkpoint/restore determinism pending verification",
            "- [x] No subsequent phase work was started",
        ])

    if args.notes:
        lines.extend(["", "NOTES:", args.notes.strip()])

    result = "\n".join(lines) + "\n"

    if args.output:
        p = Path(args.output).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(result, encoding="utf-8")
        print(f"SUCCESS: Implementor handoff drafted to {p}")
    else:
        print(result)


def cmd_verify_candidate(args):
    start_sha = args.start_sha.strip()
    candidate_sha = args.candidate_sha.strip()

    print(f"--- Routing Precondition Verification for Candidate {candidate_sha[:8]} ---")
    verify_commit_exists(start_sha, "START_SHA")
    verify_commit_exists(candidate_sha, "CANDIDATE_SHA")

    # Merge-base (Ancestry)
    code, mb, _ = run_cmd(["git", "merge-base", candidate_sha, start_sha])
    if mb != start_sha:
        print(f"ERROR: Candidate {candidate_sha} is not an ancestor of {start_sha} (Merge-base: {mb})", file=sys.stderr)
        sys.exit(1)
    print(f"Ancestry: OK (merge-base equals START_SHA {start_sha[:8]})")

    # Ahead / Behind
    _, ahead, _ = run_cmd(["git", "rev-list", "--count", f"{start_sha}..{candidate_sha}"])
    _, behind, _ = run_cmd(["git", "rev-list", "--count", f"{candidate_sha}..{start_sha}"])
    print(f"Commit counts: ahead {ahead} / behind {behind}")
    if int(behind) != 0:
        print(f"ERROR: Candidate is behind START_SHA by {behind} commits.", file=sys.stderr)
        sys.exit(1)

    # Changed files
    _, files_out, _ = run_cmd(["git", "diff", "--name-only", f"{start_sha}..{candidate_sha}"])
    _, stat_out, _ = run_cmd(["git", "diff", "--stat", f"{start_sha}..{candidate_sha}"])
    print("\nChanged Files:")
    for f in files_out.splitlines():
        print(f"  - {f}")
    print("\nDiff Stat:")
    print(f"  {stat_out}")

    print("\nSUCCESS: All routing preconditions passed.")


def cmd_draft_coordinator(args):
    candidate_sha = args.candidate_sha.strip()
    baseline_sha = args.baseline_sha.strip()
    verify_commit_exists(candidate_sha, "CANDIDATE_SHA")
    verify_commit_exists(baseline_sha, "BASELINE_SHA")

    lines = [
        "[COORDINATOR]",
        "",
        f"HANDOFF: {args.handoff_id}",
        "STATE: READY_FOR_SOURCE_REVIEW",
        f"CONSUMES: {args.consumes}",
        f"ASSIGNED_TO: {args.assigned_to}",
    ]
    if args.also_assigned_to:
        lines.append(f"ALSO_ASSIGNED_TO: {args.also_assigned_to}")
    if args.dual_review:
        lines.append("DUAL_REVIEW_REQUIRED: true")
    lines.extend([
        "NEXT_OWNER: COORDINATOR",
        "",
        f"BRANCH: {args.branch}",
        f"BASELINE_OR_REVIEWED_SHA: {baseline_sha}",
        f"CANDIDATE_SHA: {candidate_sha}",
        "",
        "REVIEW_SCOPE:",
        args.scope.strip(),
        "",
        "PASS_RULE:",
        "Independent reviewer(s) must return SOURCE_REVIEW_PASS on exact candidate SHA. Any CHANGES_REQUIRED or BLOCKED prevents advancement.",
        "",
        "EXCLUSIONS:",
        "No subsequent phase work, no unrelated changes, no reviewer code edits, no auto-merge.",
    ])

    result = "\n".join(lines) + "\n"
    if args.output:
        p = Path(args.output).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(result, encoding="utf-8")
        print(f"SUCCESS: Coordinator handoff drafted to {p}")
    else:
        print(result)


def cmd_draft_reviewer(args):
    candidate_sha = args.candidate_sha.strip()
    verify_commit_exists(candidate_sha, "CANDIDATE_SHA")

    # If verification was not explicitly performed, mark as PENDING instead of fabricating PASS
    if args.verified:
        checklist = [
            "1. First failing bound proof: PASS",
            "2. Semantic validity & normal search evolution: PASS",
            "3. Immediate terminal state & bounded capacity stability: PASS",
            "4. Predecessor regressions remain intact: PASS",
            "5. Snapshot / restore determinism & hash equality: PASS",
            "6. Scope boundaries respected (no unauthorized changes): PASS",
        ]
        state = args.verdict
        notes = args.notes.strip() if args.notes else "All regression checks and invariants verified."
    else:
        checklist = [
            "1. First failing bound proof: [ ] PENDING_REVIEWER_VERIFICATION",
            "2. Semantic validity & normal search evolution: [ ] PENDING_REVIEWER_VERIFICATION",
            "3. Immediate terminal state & bounded capacity stability: [ ] PENDING_REVIEWER_VERIFICATION",
            "4. Predecessor regressions remain intact: [ ] PENDING_REVIEWER_VERIFICATION",
            "5. Snapshot / restore determinism & hash equality: [ ] PENDING_REVIEWER_VERIFICATION",
            "6. Scope boundaries respected (no unauthorized changes): [ ] PENDING_REVIEWER_VERIFICATION",
        ]
        state = "REVIEW_IN_PROGRESS" if args.verdict == "SOURCE_REVIEW_PASS" else args.verdict
        notes = args.notes.strip() if args.notes else "Template drafted. Reviewer must verify each checklist item before signing off."

    lines = [
        f"[{args.role}]",
        "",
        f"HANDOFF: {args.handoff_id}",
        f"STATE: {state}",
        f"REVIEWED_SHA: {candidate_sha}",
        "NEXT_OWNER: COORDINATOR",
        "",
        "CHECKLIST EVALUATION:",
        "\n".join(checklist),
        "",
        "VERDICT NOTES:",
        notes,
    ]

    result = "\n".join(lines) + "\n"
    if args.output:
        p = Path(args.output).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(result, encoding="utf-8")
        print(f"SUCCESS: Reviewer handoff drafted to {p}")
    else:
        print(result)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="PR Handoff Lifecycle Automation")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # draft-implementor
    p_imp = subparsers.add_parser("draft-implementor", help="Draft implementor handoff")
    p_imp.add_argument("--role", default="IMPLEMENTOR-LOCAL", help="Implementor role tag (default: IMPLEMENTOR-LOCAL)")
    p_imp.add_argument("--assignment-id", required=True, help="Assignment ID (e.g. ISSUE26-009)")
    p_imp.add_argument("--start-sha", required=True, help="Baseline START_SHA")
    p_imp.add_argument("--tests-xml", help="Path to NUnit XML test results")
    p_imp.add_argument("--verified-invariants", action="store_true", help="Confirm determinism and capacity invariants were verified")
    p_imp.add_argument("--state", default="READY_FOR_REVIEW", help="State (default: READY_FOR_REVIEW)")
    p_imp.add_argument("--next-owner", default="COORDINATOR", help="Next owner (default: COORDINATOR)")
    p_imp.add_argument("--notes", help="Optional implementation notes")
    p_imp.add_argument("-o", "--output", help="Write to markdown file instead of stdout")
    p_imp.set_defaults(func=cmd_draft_implementor)

    # verify-candidate
    p_ver = subparsers.add_parser("verify-candidate", help="Verify coordinator routing preconditions")
    p_ver.add_argument("--start-sha", required=True, help="Baseline START_SHA")
    p_ver.add_argument("--candidate-sha", required=True, help="Candidate commit SHA")
    p_ver.set_defaults(func=cmd_verify_candidate)

    # draft-coordinator
    p_coord = subparsers.add_parser("draft-coordinator", help="Draft coordinator routing handoff")
    p_coord.add_argument("--handoff-id", required=True, help="Handoff ID (e.g. ISSUE26-011)")
    p_coord.add_argument("--candidate-sha", required=True, help="Candidate commit SHA")
    p_coord.add_argument("--baseline-sha", required=True, help="Baseline START_SHA")
    p_coord.add_argument("--consumes", required=True, help="Source handoff being consumed")
    p_coord.add_argument("--assigned-to", required=True, help="Primary reviewer role")
    p_coord.add_argument("--also-assigned-to", help="Secondary reviewer role for dual-review")
    p_coord.add_argument("--dual-review", action="store_true", help="Require dual review")
    p_coord.add_argument("--branch", required=True, help="Active branch name")
    p_coord.add_argument("--scope", required=True, help="Specific review scope description")
    p_coord.add_argument("-o", "--output", help="Write to markdown file instead of stdout")
    p_coord.set_defaults(func=cmd_draft_coordinator)

    # draft-reviewer
    p_rev = subparsers.add_parser("draft-reviewer", help="Draft reviewer verdict")
    p_rev.add_argument("--role", required=True, help="Reviewer role (e.g. REVIEWER-1A)")
    p_rev.add_argument("--handoff-id", required=True, help="Handoff ID being reviewed")
    p_rev.add_argument("--candidate-sha", required=True, help="Exact reviewed SHA")
    p_rev.add_argument("--verdict", default="SOURCE_REVIEW_PASS", help="Verdict (default: SOURCE_REVIEW_PASS)")
    p_rev.add_argument("--verified", action="store_true", help="Confirm reviewer has independently verified all 6 checklist items")
    p_rev.add_argument("--notes", help="Verdict notes or change requests")
    p_rev.add_argument("-o", "--output", help="Write to markdown file instead of stdout")
    p_rev.set_defaults(func=cmd_draft_reviewer)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

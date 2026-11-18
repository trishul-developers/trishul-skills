#!/usr/bin/env python3
r"""TTE Project Status Reporter.

Provides a single authoritative status snapshot (<60 lines) for an orchestrator or manager on waking:
- Phase branch head SHA, CI run and each job's conclusion
- Open PRs (number, branch, title, draft status)
- Remote branches by most recent commit with SHA and age (top 8)
- Ahead/behind counts relative to main
- Last 3 comments on PR and Issue (cut to ~200 chars)
- Local worktrees with branch and SHA

Uses ONLY `git` and `gh` CLI. Standard library Python 3 only.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def run_cmd(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 30) -> Tuple[int, str, str]:
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


def get_phase_ci_status(repo: str, phase_branch: str, cwd: Optional[Path] = None) -> Dict:
    # 1. Resolve phase branch HEAD SHA
    code, sha_out, _ = run_cmd(["git", "rev-parse", f"origin/{phase_branch}"], cwd=cwd)
    if code != 0 or not sha_out:
        code, sha_out, _ = run_cmd(["git", "rev-parse", phase_branch], cwd=cwd)
    head_sha = sha_out.strip() if code == 0 and sha_out else ""

    # 2. Get latest CI run for branch
    code, run_json, stderr = run_cmd([
        "gh", "run", "list",
        "--repo", repo,
        "--branch", phase_branch,
        "--limit", "1",
        "--json", "databaseId,headSha,status,conclusion,url",
    ])
    run_id = None
    run_status = "unknown"
    run_conclusion = "unknown"
    run_url = ""
    jobs = []
    gh_error = None

    if code != 0:
        first_err = stderr.splitlines()[0].strip() if stderr.strip() else f"exit code {code}"
        gh_error = first_err
    elif run_json:
        try:
            runs = json.loads(run_json)
            if runs:
                r = runs[0]
                run_id = r.get("databaseId")
                run_status = r.get("status", "unknown")
                run_conclusion = r.get("conclusion") or run_status
                run_url = r.get("url", "")
                if not head_sha:
                    head_sha = r.get("headSha", "")
        except Exception:
            pass

    if run_id:
        code_j, jobs_json, stderr_j = run_cmd([
            "gh", "run", "view", str(run_id),
            "--repo", repo,
            "--json", "jobs",
        ])
        if code_j == 0 and jobs_json:
            try:
                data = json.loads(jobs_json)
                for j in data.get("jobs", []):
                    jobs.append({
                        "name": j.get("name", "Unknown"),
                        "conclusion": j.get("conclusion") or j.get("status", "unknown"),
                    })
            except Exception:
                pass

    return {
        "head_sha": head_sha,
        "run_id": run_id,
        "status": run_status,
        "conclusion": run_conclusion,
        "url": run_url,
        "jobs": jobs,
        "error": gh_error,
    }


def get_ahead_behind(phase_branch: str, cwd: Optional[Path] = None) -> Tuple[int, int]:
    # Check origin/main vs origin/{phase_branch} or local refs
    left_ref = "origin/main"
    right_ref = f"origin/{phase_branch}"
    code, _, _ = run_cmd(["git", "rev-parse", "--verify", left_ref], cwd=cwd)
    if code != 0:
        left_ref = "main"
    code, _, _ = run_cmd(["git", "rev-parse", "--verify", right_ref], cwd=cwd)
    if code != 0:
        right_ref = phase_branch

    code, stdout, _ = run_cmd(["git", "rev-list", "--left-right", "--count", f"{left_ref}...{right_ref}"], cwd=cwd)
    if code == 0 and stdout:
        parts = stdout.split()
        if len(parts) >= 2:
            try:
                behind = int(parts[0])
                ahead = int(parts[1])
                return ahead, behind
            except ValueError:
                pass
    return 0, 0


def get_open_prs(repo: str) -> Tuple[List[Dict], Optional[str]]:
    code, stdout, stderr = run_cmd([
        "gh", "pr", "list",
        "--repo", repo,
        "--state", "open",
        "--json", "number,headRefName,title,isDraft",
    ])
    if code != 0:
        first_err = stderr.splitlines()[0].strip() if stderr.strip() else f"exit code {code}"
        return [], first_err
    if stdout:
        try:
            return json.loads(stdout), None
        except Exception:
            pass
    return [], None


def get_top_remote_branches(count: int = 8, cwd: Optional[Path] = None) -> List[Tuple[str, str, str]]:
    code, stdout, _ = run_cmd([
        "git", "for-each-ref",
        "--sort=-committerdate",
        "--format=%(refname:short)|%(objectname:short)|%(committerdate:relative)",
        "refs/remotes/origin",
    ], cwd=cwd)
    branches = []
    if code == 0 and stdout:
        for line in stdout.splitlines():
            parts = line.strip().split("|")
            if len(parts) >= 3:
                name, sha, age = parts[0], parts[1], parts[2]
                if name in ("origin", "origin/HEAD"):
                    continue
                branches.append((name, sha, age))
                if len(branches) >= count:
                    break
    return branches


def get_recent_comments(repo: str, item_type: str, item_num: int, count: int = 3) -> Tuple[List[Dict], Optional[str]]:
    cmd = ["gh", item_type, "view", str(item_num), "--repo", repo, "--json", "comments"]
    code, stdout, stderr = run_cmd(cmd)
    if code != 0:
        first_err = stderr.splitlines()[0].strip() if stderr.strip() else f"exit code {code}"
        return [], first_err
    comments = []
    if stdout:
        try:
            data = json.loads(stdout)
            all_comments = data.get("comments", [])
            for c in all_comments[-count:]:
                author_dict = c.get("author") or {}
                author = author_dict.get("login", "unknown") if isinstance(author_dict, dict) else "unknown"
                body = (c.get("body") or "").replace("\r\n", " ").replace("\n", " ").strip()
                created = c.get("createdAt", "")[:16].replace("T", " ")
                # Cut body to ~200 chars
                cut_body = body[:200] + ("..." if len(body) > 200 else "")
                comments.append({
                    "author": author,
                    "created": created,
                    "body": cut_body,
                })
        except Exception:
            pass
    return comments, None


def get_local_worktrees(cwd: Optional[Path] = None) -> List[Dict]:
    code, stdout, _ = run_cmd(["git", "worktree", "list", "--porcelain"], cwd=cwd)
    worktrees = []
    if code == 0 and stdout:
        current_wt: Dict[str, str] = {}
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                if current_wt:
                    worktrees.append(current_wt)
                    current_wt = {}
                continue
            if line.startswith("worktree "):
                current_wt["path"] = line.split(" ", 1)[1]
            elif line.startswith("HEAD "):
                current_wt["head"] = line.split(" ", 1)[1]
            elif line.startswith("branch "):
                ref = line.split(" ", 1)[1]
                current_wt["branch"] = ref.replace("refs/heads/", "")
            elif line == "detached":
                current_wt["branch"] = "(detached)"
        if current_wt:
            worktrees.append(current_wt)
    return worktrees


def format_status(
    repo: str,
    phase_branch: str,
    pr_num: int,
    issue_num: int,
    project_dir: Optional[Path] = None,
) -> str:
    lines = []
    lines.append(f"=== TTE Project Status: {repo} (local cache; does not fetch) ===")

    # 1. Phase Branch & CI Run
    ci_info = get_phase_ci_status(repo, phase_branch, cwd=project_dir)
    sha_short = (ci_info.get("head_sha") or "unknown")[:7]
    run_str = f"Run #{ci_info['run_id']} [{ci_info['conclusion'].upper()}]" if ci_info.get("run_id") else "No CI run"
    jobs_summary = ", ".join([f"{j['name']} [{j['conclusion']}]" for j in ci_info.get("jobs", [])])
    lines.append(f"Phase: {phase_branch} @ {sha_short} | CI: {run_str}")
    if ci_info.get("error"):
        lines.append(f"  gh error: {ci_info['error']}")
    elif jobs_summary:
        lines.append(f"  Jobs: {jobs_summary}")

    # 2. Ahead / Behind
    ahead, behind = get_ahead_behind(phase_branch, cwd=project_dir)
    lines.append(f"Divergence: ahead {ahead}, behind {behind} (vs main)")

    # 3. Open PRs
    prs, pr_err = get_open_prs(repo)
    lines.append(f"\nOpen PRs ({len(prs)}):")
    if pr_err:
        lines.append(f"  gh error: {pr_err}")
    elif prs:
        for p in prs[:6]:
            draft_tag = "Draft" if p.get("isDraft") else "Ready"
            title = p.get("title", "")
            if len(title) > 60:
                title = title[:57] + "..."
            lines.append(f"  #{p['number']} [{p.get('headRefName', '')}] {title} ({draft_tag})")
        if len(prs) > 6:
            lines.append(f"  ... (+{len(prs) - 6} more)")
    else:
        lines.append("  (none)")

    # 4. Top 8 Remote Branches
    top_branches = get_top_remote_branches(8, cwd=project_dir)
    lines.append(f"\nRemote Branches (top {len(top_branches)}):")
    for name, sha, age in top_branches:
        lines.append(f"  {name} @ {sha} ({age})")

    # 5. Last 3 Comments on PR
    pr_comments, pr_c_err = get_recent_comments(repo, "pr", pr_num, count=3)
    lines.append(f"\nPR #{pr_num} Last Comments ({len(pr_comments)}):")
    if pr_c_err:
        lines.append(f"  gh error: {pr_c_err}")
    elif pr_comments:
        for c in pr_comments:
            lines.append(f"  [{c['created']} @{c['author']}]: {c['body']}")
    else:
        lines.append("  (none)")

    # 6. Last 3 Comments on Issue
    issue_comments, is_c_err = get_recent_comments(repo, "issue", issue_num, count=3)
    lines.append(f"\nIssue #{issue_num} Last Comments ({len(issue_comments)}):")
    if is_c_err:
        lines.append(f"  gh error: {is_c_err}")
    elif issue_comments:
        for c in issue_comments:
            lines.append(f"  [{c['created']} @{c['author']}]: {c['body']}")
    else:
        lines.append("  (none)")

    # 7. Local Worktrees (Compact)
    wts = get_local_worktrees(cwd=project_dir)
    lines.append(f"\nLocal Worktrees ({len(wts)}):")
    for w in wts[:6]:
        p_name = Path(w.get("path", "")).name
        branch = w.get("branch", "unknown")
        head = (w.get("head", ""))[:7]
        lines.append(f"  {p_name} -> {branch} @ {head}")
    if len(wts) > 6:
        lines.append(f"  ... (+{len(wts) - 6} more)")

    # Enforce strict 60-line cap
    if len(lines) > 60:
        lines = lines[:59] + [f"... (+{len(lines) - 59} lines truncated to meet 60-line cap)"]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Authoritative Trishul Tactical Engine (TTE) Project Status snapshot (<60 lines)",
    )
    parser.add_argument(
        "--phase-branch",
        default="g02-presentation-orders-ux",
        help="Phase branch name (default: g02-presentation-orders-ux)",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=61,
        help="Phase PR number to check comments for (default: 61)",
    )
    parser.add_argument(
        "--issue",
        type=int,
        default=64,
        help="Phase question log issue number to check comments for (default: 64)",
    )
    parser.add_argument(
        "--repo",
        help="GitHub owner/repo (default: detected from origin or tosumitdhaka/trishul-tactical-engine)",
    )
    parser.add_argument(
        "-C", "--dir",
        dest="project_dir",
        default=".",
        help="Path to project checkout / worktree (default: .)",
    )

    args = parser.parse_args()
    proj_dir = Path(args.project_dir).resolve() if args.project_dir else None
    repo = detect_repo(proj_dir, args.repo)

    status_text = format_status(
        repo=repo,
        phase_branch=args.phase_branch,
        pr_num=args.pr,
        issue_num=args.issue,
        project_dir=proj_dir,
    )
    print(status_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

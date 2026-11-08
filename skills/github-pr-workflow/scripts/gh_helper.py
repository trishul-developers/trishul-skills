#!/usr/bin/env python3
"""
GitHub PR and Git Repository Helper Script.
Zero external dependencies (uses standard library Python 3).

Supports:
- Safe comment publishing from file (preventing shell escape/control character corruption)
- Fetching & filtering PR comments (e.g. by role tag [COORDINATOR], [IMPLEMENTOR-1])
- PR HEAD SHA verification
- Local git clean status and SHA verification
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run_cmd(cmd, input_text=None, cwd=None):
    res = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        cwd=cwd,
        encoding="utf-8",
        errors="replace",
    )
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def get_token():
    # 1. Environment variable
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token

    # 2. git credential helper
    code, stdout, _ = run_cmd(
        ["git", "credential", "fill"],
        input_text="protocol=https\nhost=github.com\n\n",
    )
    if code == 0 and stdout:
        for line in stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()

    print(
        "ERROR: Unable to acquire GitHub token from GITHUB_TOKEN or 'git credential fill'.",
        file=sys.stderr,
    )
    sys.exit(1)


def get_repo(repo_override=None):
    if repo_override:
        return repo_override
    code, stdout, _ = run_cmd(["git", "remote", "get-url", "origin"])
    if code != 0 or not stdout:
        print(
            "ERROR: Could not determine origin remote. Specify --repo <owner/repo> manually.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Examples:
    # https://github.com/owner/repo.git
    # git@github.com:owner/repo.git
    match = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)(?:\.git)?", stdout)
    if match:
        return f"{match.group(1)}/{match.group(2)}"

    print(
        f"ERROR: Could not parse GitHub repo from remote URL: {stdout}",
        file=sys.stderr,
    )
    sys.exit(1)


def api_request(endpoint, method="GET", data=None, repo=None):
    token = get_token()
    base_url = "https://api.github.com"
    url = f"{base_url}{endpoint}" if endpoint.startswith("/") else f"{base_url}/{endpoint}"

    headers = {
        "Authorization": f"token {token}",
        "User-Agent": "Antigravity-GitHelper",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json; charset=utf-8",
    }

    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="replace")
        print(f"HTTP ERROR {e.code} on {method} {url}: {err_msg}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR on {method} {url}: {e}", file=sys.stderr)
        sys.exit(1)


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------

def cmd_comments_list(args):
    repo = get_repo(args.repo)
    comments = api_request(f"/repos/{repo}/issues/{args.pr}/comments?per_page=100")
    
    if args.role:
        role_tag = args.role.strip()
        comments = [c for c in comments if role_tag in c.get("body", "")]

    if args.limit and len(comments) > args.limit:
        comments = comments[-args.limit :]

    print(f"--- Comments for {repo} PR #{args.pr} (Total: {len(comments)}) ---")
    for c in comments:
        cid = c.get("id")
        user = c.get("user", {}).get("login", "unknown")
        created_at = c.get("created_at", "")
        body_lines = [l.strip() for l in c.get("body", "").splitlines() if l.strip()]
        first_line = body_lines[0] if body_lines else "(empty comment)"
        print(f"[{cid}] {created_at} by @{user}: {first_line[:80]}")


def cmd_comments_get(args):
    repo = get_repo(args.repo)
    comment = api_request(f"/repos/{repo}/issues/comments/{args.comment_id}")
    print(f"=== Comment ID: {args.comment_id} by @{comment.get('user', {}).get('login')} at {comment.get('created_at')} ===")
    print(comment.get("body", ""))


def cmd_comments_post(args):
    repo = get_repo(args.repo)
    if args.file:
        if not os.path.exists(args.file):
            print(f"ERROR: Payload file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    elif args.body:
        content = args.body
    else:
        print("ERROR: Either --file or --body is required.", file=sys.stderr)
        sys.exit(1)

    # Invariant validation: check for unwanted control characters like form feed \x0c
    if "\x0c" in content:
        print("WARNING: Found Form Feed '\\x0c' character in comment payload. Stripping it.", file=sys.stderr)
        content = content.replace("\x0c", "")

    data = {"body": content}
    result = api_request(f"/repos/{repo}/issues/{args.pr}/comments", method="POST", data=data)
    cid = result.get("id")
    html_url = result.get("html_url")
    print(f"SUCCESS: Comment published to {repo} PR #{args.pr}")
    print(f"Comment ID: {cid}")
    print(f"URL: {html_url}")


def cmd_pr_verify(args):
    repo = get_repo(args.repo)
    pr = api_request(f"/repos/{repo}/pulls/{args.pr}")
    head_sha = pr.get("head", {}).get("sha")
    head_ref = pr.get("head", {}).get("ref")
    state = pr.get("state")

    print(f"PR #{args.pr} State: {state}")
    print(f"Remote Head Ref: {head_ref}")
    print(f"Remote Head SHA: {head_sha}")

    if args.sha:
        if head_sha != args.sha:
            print(f"ERROR: SHA MISMATCH! Expected {args.sha} but remote PR HEAD is {head_sha}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"SUCCESS: Remote PR #{args.pr} HEAD matches expected SHA: {args.sha}")

    if args.branch:
        if head_ref != args.branch:
            print(f"ERROR: BRANCH MISMATCH! Expected {args.branch} but remote PR branch is {head_ref}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"SUCCESS: Remote PR #{args.pr} branch matches expected: {args.branch}")


def cmd_git_verify(args):
    cwd = getattr(args, "repo_dir", None)
    if cwd:
        cwd = str(Path(cwd).resolve())

    # 1. Clean status
    code, stdout, _ = run_cmd(["git", "status", "--porcelain"], cwd=cwd)
    if code != 0:
        print("ERROR: Failed to run git status", file=sys.stderr)
        sys.exit(1)
    if stdout:
        print("ERROR: Working tree is not clean:", file=sys.stderr)
        print(stdout, file=sys.stderr)
        sys.exit(1)
    print("Working tree: CLEAN")

    # 2. Current branch
    code, current_branch, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    print(f"Current branch: {current_branch}")
    if args.branch and current_branch != args.branch:
        print(f"ERROR: Expected branch '{args.branch}', found '{current_branch}'", file=sys.stderr)
        sys.exit(1)

    # 3. Current SHA
    code, current_sha, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=cwd)
    print(f"Current HEAD SHA: {current_sha}")
    if args.sha and current_sha != args.sha:
        print(f"ERROR: Expected HEAD SHA '{args.sha}', found '{current_sha}'", file=sys.stderr)
        sys.exit(1)

    print("SUCCESS: Local git verification passed.")


# ----------------------------------------------------------------------
# CI Digest
# ----------------------------------------------------------------------

def strip_log_prefix(line: str) -> str:
    """Strip workflow runner and timestamp prefixes from log line."""
    line = re.sub(r"^[^\t\r\n]+\t[^\t\r\n]+\t\d{4}-\d{2}-\d{2}T[^\s]+\s+", "", line)
    line = re.sub(r"^\d{4}-\d{2}-\d{2}T[^\s]+\s+", "", line)
    return line.strip()


def parse_tte_ci_job_log(repo: str, run_id: int, job_id: int, max_failures: int = 10):
    """Attempt to parse TTE CI summary table and 'First failures' block from job log."""
    code, stdout, _ = run_cmd([
        "gh", "run", "view", str(run_id),
        "--repo", repo,
        "--job", str(job_id),
        "--log",
    ])
    if code != 0 or not stdout:
        return None

    clean_lines = [strip_log_prefix(l) for l in stdout.splitlines()]
    counts = None
    failures = []

    for idx, l in enumerate(clean_lines):
        if l.startswith("| total |") and counts is None and idx + 2 < len(clean_lines):
            data_line = clean_lines[idx + 2]
            parts = [p.strip() for p in data_line.split("|") if p.strip()]
            if len(parts) >= 4:
                try:
                    counts = {
                        "total": int(parts[0]),
                        "passed": int(parts[1]),
                        "failed": int(parts[2]),
                        "skipped": int(parts[3]),
                    }
                except ValueError:
                    pass

        if "First failures" in l and not failures:
            for f_idx in range(idx + 1, min(idx + 1 + max_failures + 30, len(clean_lines))):
                f_line = clean_lines[f_idx]
                if f_line.startswith("##[") or f_line.startswith("### "):
                    break
                if not f_line or f_line.startswith("|"):
                    continue
                if f_line.startswith("- ") or f_line.startswith("* "):
                    item = f_line[2:].strip()
                    if ":" in item:
                        name_part, msg_part = item.split(":", 1)
                        name = name_part.strip().strip("`")
                        msg = msg_part.strip()
                        failures.append((name, msg))
                    else:
                        failures.append((item.strip("`"), ""))

        if counts and failures and l.startswith("### "):
            break

    if counts or failures:
        return {"counts": counts, "failures": failures[:max_failures]}
    return None


def parse_nunit_artifact(repo: str, run_id: int, job_name: str, max_failures: int = 10):
    """Fallback: download NUnit XML artifacts and parse test counts and failures."""
    import tempfile
    import xml.etree.ElementTree as ET

    with tempfile.TemporaryDirectory() as tmpdir:
        code, _, _ = run_cmd(["gh", "run", "download", str(run_id), "--repo", repo, "--dir", tmpdir])
        if code != 0:
            return None

        xml_files = list(Path(tmpdir).rglob("*.xml"))
        if not xml_files:
            return None

        target_xml = xml_files[0]
        for xf in xml_files:
            if "editmode" in job_name.lower() and "editmode" in xf.name.lower():
                target_xml = xf
                break
            if "playmode" in job_name.lower() and "playmode" in xf.name.lower():
                target_xml = xf
                break

        try:
            tree = ET.parse(target_xml)
            root = tree.getroot()
            counts = {
                "total": int(root.attrib.get("total", 0)),
                "passed": int(root.attrib.get("passed", 0)),
                "failed": int(root.attrib.get("failed", 0)),
                "skipped": int(root.attrib.get("skipped", 0)),
            }
            failures = []
            for tc in root.iter("test-case"):
                res = tc.attrib.get("result", "")
                if res.lower() in ("failed", "failure"):
                    name = tc.attrib.get("fullname") or tc.attrib.get("name") or "UnknownTest"
                    fail_node = tc.find("failure")
                    msg = fail_node.findtext("message") if fail_node is not None else ""
                    failures.append((name, (msg or "").strip()))
            return {"counts": counts, "failures": failures[:max_failures]}
        except Exception:
            return None


def extract_job_error_lines(repo: str, run_id: int, job_id: int):
    """Extract compiler error CS lines or general failure lines from job log."""
    code, stdout, _ = run_cmd([
        "gh", "run", "view", str(run_id),
        "--repo", repo,
        "--job", str(job_id),
        "--log",
    ])
    if code != 0 or not stdout:
        return []

    errors = []
    for line in stdout.splitlines():
        cl = strip_log_prefix(line)
        if ": error CS" in cl or ": error" in cl.lower() or "BuildFailedException:" in cl:
            errors.append(cl)
        elif "##[error]" in cl:
            errors.append(cl.replace("##[error]", "").strip())
    return errors[:5]


def cmd_ci_digest(args):
    repo = get_repo(getattr(args, "repo", None))
    run_id = getattr(args, "run_id", None)
    branch = getattr(args, "branch", None)
    max_failures = getattr(args, "max_failures", 10)

    # 1. Resolve run_id if not given
    if not run_id:
        if not branch:
            code, curr_branch, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
            if code == 0 and curr_branch and curr_branch != "HEAD":
                branch = curr_branch
            else:
                branch = "main"

        code, stdout, _ = run_cmd([
            "gh", "run", "list",
            "--repo", repo,
            "--branch", branch,
            "--limit", "1",
            "--json", "databaseId,headSha,status,conclusion,url",
        ])
        if code == 0 and stdout:
            try:
                runs = json.loads(stdout)
                if runs:
                    run_id = runs[0].get("databaseId")
            except Exception:
                pass

        if not run_id:
            try:
                data = api_request(f"/repos/{repo}/actions/runs?branch={branch}&per_page=1")
                runs = data.get("workflow_runs", [])
                if runs:
                    run_id = runs[0].get("id")
            except Exception:
                pass

        if not run_id:
            print(f"ERROR: No CI workflow runs found for branch '{branch}' in {repo}.", file=sys.stderr)
            sys.exit(1)

    # 2. Fetch run details & jobs
    run_info = None
    code, stdout, _ = run_cmd([
        "gh", "run", "view", str(run_id),
        "--repo", repo,
        "--json", "databaseId,headSha,headBranch,status,conclusion,url,jobs,name",
    ])
    if code == 0 and stdout:
        try:
            run_info = json.loads(stdout)
        except Exception:
            pass

    if not run_info:
        run_data = api_request(f"/repos/{repo}/actions/runs/{run_id}")
        jobs_data = api_request(f"/repos/{repo}/actions/runs/{run_id}/jobs")
        run_info = {
            "databaseId": run_data.get("id"),
            "headSha": run_data.get("head_sha"),
            "headBranch": run_data.get("head_branch"),
            "status": run_data.get("status"),
            "conclusion": run_data.get("conclusion"),
            "url": run_data.get("html_url"),
            "name": run_data.get("name"),
            "jobs": jobs_data.get("jobs", []),
        }

    run_url = run_info.get("url") or f"https://github.com/{repo}/actions/runs/{run_id}"
    head_sha = (run_info.get("headSha") or "")[:7]
    head_branch = run_info.get("headBranch") or ""
    conclusion = (run_info.get("conclusion") or run_info.get("status") or "UNKNOWN").upper()

    lines = []
    lines.append(f"=== CI Digest: {run_info.get('name', 'Run')} #{run_id} ===")
    lines.append(f"Run URL: {run_url}")
    lines.append(f"Branch:  {head_branch} @ {head_sha} | Verdict: [{conclusion}]")
    lines.append("")
    lines.append("Jobs:")

    jobs = run_info.get("jobs", [])
    for j in jobs:
        j_id = j.get("id") or j.get("databaseId")
        j_name = j.get("name", "Unnamed")
        j_status = j.get("status", "")
        j_concl = (j.get("conclusion") or j_status or "UNKNOWN").upper()

        lines.append(f"- [{j_concl}] {j_name}")
        # Parse test counts for passing as well as failing jobs
        parsed = parse_tte_ci_job_log(repo, run_id, j_id, max_failures)
        if not parsed:
            parsed = parse_nunit_artifact(repo, run_id, j_name, max_failures)

        if parsed and parsed.get("counts"):
            c = parsed["counts"]
            lines.append(f"    Tests: {c.get('passed', 0)} passed, {c.get('failed', 0)} failed, {c.get('skipped', 0)} skipped (total {c.get('total', 0)})")

        if j_concl == "FAILURE":
            if parsed and parsed.get("failures"):
                fails = parsed["failures"]
                lines.append(f"    First failures ({len(fails)}):")
                for name, msg in fails[:max_failures]:
                    msg_str = f": {msg[:200]}" if msg else ""
                    lines.append(f"    * `{name}`{msg_str}")
            elif not (parsed and parsed.get("counts")):
                err_lines = extract_job_error_lines(repo, run_id, j_id)
                if err_lines:
                    lines.append("    Errors:")
                    for el in err_lines[:5]:
                        lines.append(f"    * {el}")

    # Enforce strict 50-line cap
    flat_lines = []
    for l in lines:
        flat_lines.extend(l.splitlines())
    if len(flat_lines) > 50:
        flat_lines = flat_lines[:49] + [f"... (+{len(flat_lines) - 49} lines truncated to meet 50-line cap)"]

    print("\n".join(flat_lines))


# ----------------------------------------------------------------------
# CLI Setup
# ----------------------------------------------------------------------

def main():
    repo_parent = argparse.ArgumentParser(add_help=False)
    repo_parent.add_argument("--repo", default=argparse.SUPPRESS, help="Repository in 'owner/repo' format (defaults to origin URL)")

    parser = argparse.ArgumentParser(description="GitHub PR and Git repository helper", parents=[repo_parent])

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # comments
    p_comments = subparsers.add_parser("comments", help="PR comment operations", parents=[repo_parent])
    c_sub = p_comments.add_subparsers(dest="action", required=True)

    # comments list
    c_list = c_sub.add_parser("list", help="List comments on a PR", parents=[repo_parent])
    c_list.add_argument("--pr", "--issue", dest="pr", required=True, type=int, help="PR or Issue number")
    c_list.add_argument("--limit", type=int, default=10, help="Max comments to display")
    c_list.add_argument("--role", help="Filter by substring/role (e.g. '[COORDINATOR]')")
    c_list.set_defaults(func=cmd_comments_list)

    # comments get
    c_get = c_sub.add_parser("get", help="Get full body of a comment", parents=[repo_parent])
    c_get.add_argument("--comment-id", required=True, help="Comment ID")
    c_get.set_defaults(func=cmd_comments_get)

    # comments post
    c_post = c_sub.add_parser("post", help="Post a comment to a PR", parents=[repo_parent])
    c_post.add_argument("--pr", "--issue", dest="pr", required=True, type=int, help="PR or Issue number")
    c_post.add_argument("--file", "--body-file", dest="file", help="Path to markdown/text file containing comment body")
    c_post.add_argument("--body", help="Inline body string")
    c_post.set_defaults(func=cmd_comments_post)

    # comment (convenience alias for comments post)
    p_comment = subparsers.add_parser("comment", help="Alias for 'comments post'", parents=[repo_parent])
    p_comment.add_argument("--pr", "--issue", dest="pr", required=True, type=int, help="PR or Issue number")
    p_comment.add_argument("--file", "--body-file", dest="file", help="Path to markdown/text file containing comment body")
    p_comment.add_argument("--body", help="Inline body string")
    p_comment.set_defaults(func=cmd_comments_post)

    # pr
    p_pr = subparsers.add_parser("pr", help="Pull request operations", parents=[repo_parent])
    pr_sub = p_pr.add_subparsers(dest="action", required=True)

    # pr verify
    pr_verify = pr_sub.add_parser("verify", help="Verify PR remote HEAD and branch", parents=[repo_parent])
    pr_verify.add_argument("--pr", "--issue", dest="pr", required=True, type=int, help="PR or Issue number")
    pr_verify.add_argument("--sha", help="Expected HEAD commit SHA")
    pr_verify.add_argument("--branch", help="Expected branch name")
    pr_verify.set_defaults(func=cmd_pr_verify)

    # git
    p_git = subparsers.add_parser("git", help="Local git verification", parents=[repo_parent])
    git_sub = p_git.add_subparsers(dest="action", required=True)

    # git verify
    g_verify = git_sub.add_parser("verify", help="Verify clean tree, branch, and SHA", parents=[repo_parent])
    g_verify.add_argument("-C", "--dir", dest="repo_dir", help="Path to repository root")
    g_verify.add_argument("--branch", help="Expected branch name")
    g_verify.add_argument("--sha", help="Expected commit SHA")
    g_verify.set_defaults(func=cmd_git_verify)

    # verify-clean (convenience alias for git verify)
    p_vc = subparsers.add_parser("verify-clean", help="Alias for 'git verify'", parents=[repo_parent])
    p_vc.add_argument("-C", "--dir", dest="repo_dir", help="Path to repository root")
    p_vc.add_argument("--branch", help="Expected branch name")
    p_vc.add_argument("--sha", help="Expected commit SHA")
    p_vc.set_defaults(func=cmd_git_verify)

    # ci
    p_ci = subparsers.add_parser("ci", help="CI workflow and run operations", parents=[repo_parent])
    ci_sub = p_ci.add_subparsers(dest="action", required=True)

    # Shared parser for ci digest and ci-digest
    p_digest_opts = argparse.ArgumentParser(add_help=False)
    p_digest_opts.add_argument("--run-id", type=int, help="Workflow run database ID")
    p_digest_opts.add_argument("--branch", help="Branch name (fetches latest run for this branch)")
    p_digest_opts.add_argument("--max-failures", type=int, default=10, help="Max failure lines to show (default: 10)")

    # ci digest
    c_digest = ci_sub.add_parser("digest", help="Digest CI run or branch into compact summary", parents=[repo_parent, p_digest_opts])
    c_digest.set_defaults(func=cmd_ci_digest)

    # ci-digest (convenience alias for 'ci digest')
    p_cid = subparsers.add_parser("ci-digest", help="Alias for 'ci digest'", parents=[repo_parent, p_digest_opts])
    p_cid.set_defaults(func=cmd_ci_digest)

    args = parser.parse_args()
    if not hasattr(args, "repo"):
        args.repo = None
    args.func(args)


if __name__ == "__main__":
    main()

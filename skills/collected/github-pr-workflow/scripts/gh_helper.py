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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run_cmd(cmd, input_text=None):
    res = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
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
    # 1. Clean status
    code, stdout, _ = run_cmd(["git", "status", "--porcelain"])
    if code != 0:
        print("ERROR: Failed to run git status", file=sys.stderr)
        sys.exit(1)
    if stdout:
        print("ERROR: Working tree is not clean:", file=sys.stderr)
        print(stdout, file=sys.stderr)
        sys.exit(1)
    print("Working tree: CLEAN")

    # 2. Current branch
    code, current_branch, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    print(f"Current branch: {current_branch}")
    if args.branch and current_branch != args.branch:
        print(f"ERROR: Expected branch '{args.branch}', found '{current_branch}'", file=sys.stderr)
        sys.exit(1)

    # 3. Current SHA
    code, current_sha, _ = run_cmd(["git", "rev-parse", "HEAD"])
    print(f"Current HEAD SHA: {current_sha}")
    if args.sha and current_sha != args.sha:
        print(f"ERROR: Expected HEAD SHA '{args.sha}', found '{current_sha}'", file=sys.stderr)
        sys.exit(1)

    print("SUCCESS: Local git verification passed.")


# ----------------------------------------------------------------------
# CLI Setup
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="GitHub PR and Git repository helper")
    parser.add_argument("--repo", help="Repository in 'owner/repo' format (defaults to origin URL)")

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # comments
    p_comments = subparsers.add_parser("comments", help="PR comment operations")
    c_sub = p_comments.add_subparsers(dest="action", required=True)

    # comments list
    c_list = c_sub.add_parser("list", help="List comments on a PR")
    c_list.add_argument("--pr", required=True, type=int, help="PR number")
    c_list.add_argument("--limit", type=int, default=10, help="Max comments to display")
    c_list.add_argument("--role", help="Filter by substring/role (e.g. '[COORDINATOR]')")
    c_list.set_defaults(func=cmd_comments_list)

    # comments get
    c_get = c_sub.add_parser("get", help="Get full body of a comment")
    c_get.add_argument("--comment-id", required=True, help="Comment ID")
    c_get.set_defaults(func=cmd_comments_get)

    # comments post
    c_post = c_sub.add_parser("post", help="Post a comment to a PR")
    c_post.add_argument("--pr", required=True, type=int, help="PR number")
    c_post.add_argument("--file", help="Path to markdown/text file containing comment body")
    c_post.add_argument("--body", help="Inline body string")
    c_post.set_defaults(func=cmd_comments_post)

    # pr
    p_pr = subparsers.add_parser("pr", help="Pull request operations")
    pr_sub = p_pr.add_subparsers(dest="action", required=True)

    # pr verify
    pr_verify = pr_sub.add_parser("verify", help="Verify PR remote HEAD and branch")
    pr_verify.add_argument("--pr", required=True, type=int, help="PR number")
    pr_verify.add_argument("--sha", help="Expected HEAD commit SHA")
    pr_verify.add_argument("--branch", help="Expected branch name")
    pr_verify.set_defaults(func=cmd_pr_verify)

    # git
    p_git = subparsers.add_parser("git", help="Local git verification")
    git_sub = p_git.add_subparsers(dest="action", required=True)

    # git verify
    g_verify = git_sub.add_parser("verify", help="Verify clean tree, branch, and SHA")
    g_verify.add_argument("--branch", help="Expected branch name")
    g_verify.add_argument("--sha", help="Expected commit SHA")
    g_verify.set_defaults(func=cmd_git_verify)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

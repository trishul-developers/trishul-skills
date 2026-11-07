#!/usr/bin/env python3
"""GitHub PR comment and local git helper. Requires Python 3 and gh CLI."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def run(argv, cwd=None):
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", check=False)
    except FileNotFoundError as e:
        raise RuntimeError(f"Executable unavailable: {argv[0]}") from e
    if p.returncode:
        raise RuntimeError(f"{' '.join(argv[:3])} failed ({p.returncode}): {p.stderr.strip()}")
    return p.stdout


def comments(repo, pr):
    raw = run(["gh", "api", "--paginate", "--slurp", "-H", "Accept: application/vnd.github+json",
               f"repos/{repo}/issues/{pr}/comments?per_page=100"])
    pages = json.loads(raw)
    rows = [item for page in pages for item in page] if pages and isinstance(pages[0], list) else pages
    return sorted(rows, key=lambda c: (c.get("created_at", ""), int(c["id"])))


def git(repo_dir, *args):
    return run(["git", "-C", str(repo_dir), *args]).strip()


def verify(args):
    root = Path(args.repo_dir).resolve()
    if git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise RuntimeError("Working tree is not clean")
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = git(root, "rev-parse", "HEAD")
    expected = git(root, "rev-parse", "--verify", f"{args.expected_sha}^{{commit}}")
    if branch != args.branch:
        raise RuntimeError(f"Branch mismatch: {branch} != {args.branch}")
    behind, ahead = map(int, git(root, "rev-list", "--left-right", "--count", f"{expected}...{head}").split())
    if behind or (not args.allow_descendant and head != expected):
        raise RuntimeError(f"SHA/ancestry mismatch: HEAD={head}, expected={expected}, behind={behind}, ahead={ahead}")
    print(f"VERIFIED branch={branch} HEAD={head} expected={expected} behind={behind} ahead={ahead}")


def main():
    p = argparse.ArgumentParser()
    groups = p.add_subparsers(dest="group", required=True)
    c = groups.add_parser("comments").add_subparsers(dest="action", required=True)
    li = c.add_parser("list"); li.add_argument("--repo", required=True); li.add_argument("--pr", type=int, required=True)
    get = c.add_parser("get"); get.add_argument("--repo", required=True); get.add_argument("--comment-id", type=int, required=True)
    post = c.add_parser("post"); post.add_argument("--repo", required=True); post.add_argument("--pr", type=int, required=True); post.add_argument("--file", type=Path, required=True)
    v = groups.add_parser("git").add_subparsers(dest="action", required=True).add_parser("verify")
    v.add_argument("--repo-dir", type=Path, required=True); v.add_argument("--expected-sha", required=True)
    v.add_argument("--branch", required=True); v.add_argument("--allow-descendant", action="store_true")
    a = p.parse_args()
    if a.group == "git":
        verify(a); return
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", a.repo):
        raise ValueError("--repo must be OWNER/REPO")
    if a.action == "list":
        for row in comments(a.repo, a.pr):
            print(f"{row['id']}\t{row.get('created_at','')}\t{row.get('user',{}).get('login','')}\t{row.get('body','').splitlines()[0] if row.get('body') else ''}")
    elif a.action == "get":
        row = json.loads(run(["gh", "api", f"repos/{a.repo}/issues/comments/{a.comment_id}"]))
        sys.stdout.write(row.get("body", ""))
    else:
        if not a.file.is_file():
            raise ValueError(f"Comment file does not exist: {a.file}")
        body = a.file.read_text(encoding="utf-8")
        if not body.strip() or any(ch in body for ch in ("\x00", "\x0c")):
            raise ValueError("Comment is empty or contains an invalid control character")
        print(run(["gh", "pr", "comment", str(a.pr), "--repo", a.repo, "--body-file", str(a.file)]).strip())


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

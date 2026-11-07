---
name: github-pr-git-workflow
description: >-
  Use this skill for inspecting GitHub PR comments, publishing formatted handoffs or PR comments safely without shell corruption, and executing git repository verification tasks (clean status, exact SHA matching, fast-forward pushing, and remote PR HEAD verification).
---

# GitHub PR and Git Repository Workflow

This skill provides step-by-step procedures and an executable, zero-dependency Python helper (`scripts/gh_helper.py`) for interacting with GitHub Pull Requests and validating git repository state on Windows and cross-platform environments.

## Why Use the Helper Script?

1. **Eliminates Shell Corruption Bugs**: In PowerShell, constructing markdown strings in expandable quotes (`@"..."@`) treats backticks as escape characters (e.g. `` `f `` becomes Form Feed `\x0c`), mangling branch names and commit SHAs in GitHub comments. The helper reads comment bodies directly from UTF-8 files, preventing any shell escaping or encoding corruption.
2. **Zero Setup Required**: Automatically retrieves credentials from `git credential fill` or `GITHUB_TOKEN`. Does not require `gh.exe` to be installed on the machine.
3. **Structured Role Filtering**: Easily filters PR comments by role tag (`[COORDINATOR]`, `[IMPLEMENTOR-1]`, `[REVIEWER]`).
4. **Authoritative Git Verification**: Enforces clean working trees, exact SHA matching, and remote PR HEAD alignment.

---

## Quick Reference Commands

Helper script path:
`.agents/skills/github-pr-git-workflow/scripts/gh_helper.py`

### 1. Check GitHub PR Comments

Inspect recent comments or locate the latest handoff for a specific role:

```powershell
# List recent comments on PR #28 (default limit 10)
python .agents/skills/github-pr-git-workflow/scripts/gh_helper.py comments list --pr 28 --limit 10

# Filter comments by role tag (e.g. [COORDINATOR] or [IMPLEMENTOR-1])
python .agents/skills/github-pr-git-workflow/scripts/gh_helper.py comments list --pr 28 --role "[COORDINATOR]"

# View the full body of a specific comment by its ID
python .agents/skills/github-pr-git-workflow/scripts/gh_helper.py comments get --comment-id <COMMENT_ID>
```

---

### 2. Properly Publish a PR Comment / Handoff

Never pass raw multiline markdown in inline PowerShell strings. Always follow this file-based procedure:

1. **Write the Comment Body to a File**:
   Create a markdown file (e.g. in your scratch directory or brain artifact folder):
   ```powershell
   # Write handoff content cleanly to a file (e.g. scratch/handoff.md)
   ```

2. **Verify Formatting Invariants**:
   - Ensure branch names and commit SHAs are plain ASCII (e.g., `fix/issue-26-phases-05-09-remediation`, not prefixed with stray backslashes like `\fix/...`).
   - Ensure all role tags, commit logs, and test evidence are included as required by the role contract.

3. **Publish via the Helper Script**:
   ```powershell
   python .agents/skills/github-pr-git-workflow/scripts/gh_helper.py comments post --pr 28 --file scratch/handoff.md
   ```

The script will read the file in UTF-8, sanitize any inadvertent control codes, submit it to the GitHub REST API, and output the created comment ID and URL.

---

### 3. Verify Git Repository State & Push

Before editing, verify that your local repository matches the required assignment state. After editing, verify additive commits and push:

```powershell
# Verify working tree is clean and inspect current branch & HEAD SHA
python .agents/skills/github-pr-git-workflow/scripts/gh_helper.py git verify

# Verify exact branch and START_SHA before starting implementation
python .agents/skills/github-pr-git-workflow/scripts/gh_helper.py git verify --branch fix/issue-26-phases-05-09-remediation --sha <START_SHA>

# Push additive commits to remote (fast-forward only)
git push origin fix/issue-26-phases-05-09-remediation

# Verify that remote PR HEAD matches your local FINAL_SHA
python .agents/skills/github-pr-git-workflow/scripts/gh_helper.py pr verify --pr 28 --sha <FINAL_SHA>
```

---

### 4. Watch for New Coordinator Role Assignments

Use `gh_watch.py` to automatically detect incoming `[COORDINATOR]` assignments to `IMPLEMENTOR-1`:

```powershell
# Check for any new unconsumed assignment on PR #28:
python .agents/skills/github-pr-git-workflow/scripts/gh_watch.py check

# Mark a handoff as consumed once handled:
python .agents/skills/github-pr-git-workflow/scripts/gh_watch.py mark-consumed ISSUE26-020

# View current watcher state:
python .agents/skills/github-pr-git-workflow/scripts/gh_watch.py status
```

---

## Rules & Guardrails

- **Additive Commits Only**: Never run `git commit --amend`, `git rebase`, `git reset`, `git squash`, or `git push --force`.
- **Superseding Comments**: If a prior handoff comment contained formatting or typographical errors, do not attempt to delete or edit it. Post a new top-level comment explicitly stating:
  `SUPERSEDES: prior malformed-format <HANDOFF_ID> handoff`
- **Plain ASCII**: Never prefix SHAs or branch names with backslashes.

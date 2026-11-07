---
name: github-pr-workflow
description: Complete GitHub Pull Request workflow automation: zero-dependency GitHub API interactions (via pure Python urllib), safe multi-line comment publishing from file (preventing shell quoting corruption), PR comment polling and role watching, HEAD SHA matching, and local git clean status verification.
compatibility: Platform independent. Python 3 standard library only (no gh CLI dependency required).
tags: [git, github, pull-request, watcher, comments, handoff]
---

# Unified GitHub PR Workflow

This skill provides an authoritative, zero-dependency suite for GitHub Pull Request operations, safe multi-line comment publishing, and automated role handoff polling across multi-agent workflows.

## Core Capabilities
- **Safe Comment Publishing**: `scripts/gh_helper.py comment --pr <N> --body-file <PATH>` uses Python `urllib` to post directly to GitHub's REST API, eliminating shell escaping corruption on Windows.
- **PR Comment & Role Watching**: `scripts/gh_watch.py` monitors PR comments for role transitions (e.g. `[COORDINATOR]`, `[IMPLEMENTOR-1]`), verifies `START_SHA` against local `git rev-parse HEAD`, and persists state in `pr_watch_state.json` to prevent duplicate execution loops.
- **Handoff Router Polling**: `scripts/pr_handoff_router_poll.py` enables automated scheduled polling without waking models when there is no new activity.
- **Repository Verification**: `scripts/gh_helper.py check-head` and `verify-clean` guarantee working trees are clean and fast-forward pushing is safe.

## Quickstart Recipes

### 1. Safely Publishing a PR Comment from File
```bash
python "skills/collected/github-pr-workflow/scripts/gh_helper.py" comment \
  --repo "tosumitdhaka/trishul-tactical-engine" \
  --pr 28 \
  --body-file "briefs/handoff-block.md"
```

### 2. Checking Local Git Status & SHA
```bash
python "skills/collected/github-pr-workflow/scripts/gh_helper.py" verify-clean \
  -C "E:/Projects/trishul-tactical-engine"
```

### 3. Watching for Role Assignments
```bash
python "skills/collected/github-pr-workflow/scripts/gh_watch.py" \
  --repo "tosumitdhaka/trishul-tactical-engine" \
  --pr 28 \
  --role "IMPLEMENTOR-1" \
  --state-file "state/pr28_watch.json"
```

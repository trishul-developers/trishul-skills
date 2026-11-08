---
name: github-pr-workflow
description: Complete GitHub Pull Request and CI workflow automation: zero-dependency GitHub API interactions (via pure Python urllib), safe multi-line comment publishing from file (preventing shell quoting corruption), CI run failure & test digestion (<=50 lines), PR comment polling and role watching, HEAD SHA matching, and local git clean status verification.
compatibility: Platform independent. Python 3 standard library only.
tags: [git, github, pull-request, watcher, comments, handoff, ci, digest]
---

# Unified GitHub PR & CI Workflow

This skill provides an authoritative, zero-dependency suite for GitHub Pull Request operations, safe multi-line comment publishing, compact CI failure digests, and automated role handoff polling across multi-agent workflows.

## Core Capabilities
- **Safe Comment Publishing**: `scripts/gh_helper.py comments post --pr <N> --file <PATH>` (or convenience alias `comment --pr <N> --body-file <PATH>`) uses Python `urllib` to post directly to GitHub's REST API, eliminating shell escaping corruption on Windows.
- **CI Run Failure & Test Digest**: `scripts/gh_helper.py ci digest --branch <branch>` (or `--run-id <id>`) parses job conclusions, test counts (total, passed, failed, skipped), and first failing test names + messages directly from TTE CI summary log tables or NUnit XML artifacts into $\le 50$ lines, eliminating costly manual log scraping.
- **PR Comment & Role Watching**: `scripts/gh_watch.py` monitors PR comments for role transitions (e.g. `[COORDINATOR]`, `[IMPLEMENTOR-1]`), verifies `START_SHA` against local `git rev-parse HEAD`, and persists state in `pr_watch_state.json` to prevent duplicate execution loops.
- **Handoff Router Polling**: `scripts/pr_handoff_router_poll.py` enables automated scheduled polling without waking models when there is no new activity.
- **Repository Verification**: `scripts/gh_helper.py git verify` (or convenience alias `verify-clean -C <dir>`) guarantees working trees are clean and fast-forward pushing is safe.

## Quickstart Recipes

### 1. Digesting a CI Run or Branch (<50 lines)
```bash
python "skills/github-pr-workflow/scripts/gh_helper.py" ci digest \
  --repo "tosumitdhaka/trishul-tactical-engine" \
  --branch "g02-presentation-orders-ux"
```
Or by run ID:
```bash
python "skills/github-pr-workflow/scripts/gh_helper.py" ci digest \
  --run-id 42323789243
```

### 2. Safely Publishing a PR Comment from File
```bash
python "skills/github-pr-workflow/scripts/gh_helper.py" comments post \
  --repo "tosumitdhaka/trishul-tactical-engine" \
  --pr 28 \
  --file "scratch/handoff-block.md"
```

### 3. Checking Local Git Status & SHA
```bash
python "skills/github-pr-workflow/scripts/gh_helper.py" git verify \
  -C "<repo_dir>"
```

### 4. Watching for Role Assignments
```bash
python "skills/github-pr-workflow/scripts/gh_watch.py" \
  --repo "tosumitdhaka/trishul-tactical-engine" \
  --pr 28 \
  --role "IMPLEMENTOR-1" \
  --state-file "state/pr28_watch.json"
```

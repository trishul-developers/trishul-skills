---
name: github-pr-workflow
description: Complete GitHub Pull Request and CI workflow automation: zero-dependency GitHub API interactions (via pure Python urllib), safe multi-line comment publishing from file (preventing shell quoting corruption), CI run failure & test digestion (<=50 lines), quiet CI run waiting and wake-up notifications (ci wait), PR comment polling and role watching, HEAD SHA matching, and local git clean status verification.
compatibility: Platform independent. Python 3 standard library only.
tags: [git, github, pull-request, watcher, comments, handoff, ci, digest, ci-wait, wait]
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
python "<skill-dir>/scripts/gh_helper.py" ci digest \
  --repo "<owner>/<repo>" \
  --branch "<branch>"
```
Or by run ID:
```bash
python "<skill-dir>/scripts/gh_helper.py" ci digest \
  --run-id <run-id>
```

### 2. Safely Publishing a PR Comment from File
```bash
python "<skill-dir>/scripts/gh_helper.py" comments post \
  --repo "<owner>/<repo>" \
  --pr <N> \
  --file "scratch/handoff-block.md"
```

### 3. Checking Local Git Status & SHA
```bash
python "<skill-dir>/scripts/gh_helper.py" git verify \
  -C "<repo_dir>"
```

### 4. Watching for Role Assignments
```bash
python "<skill-dir>/scripts/gh_watch.py" \
  --repo "<owner>/<repo>" \
  --pr <N> \
  --role "IMPLEMENTOR-1" \
  --state-file ".local/pr_watch_state.json"
```

### 5. Waiting for CI Workflow Completion (`ci wait`)
```bash
python "<skill-dir>/scripts/gh_helper.py" ci wait \
  --repo "<owner>/<repo>" \
  --sha <sha>
```
Or by workflow run ID:
```bash
python "<skill-dir>/scripts/gh_helper.py" ci wait \
  --repo "<owner>/<repo>" \
  --run-id <run-id> \
  --interval 15
```

---

## Waking a chat when CI finishes (ci wait)

When an orchestrator or worker agent pushes commits to GitHub, CI starts asynchronously. Rather than sitting idle or burning model turns on active polling, agents can wake themselves up automatically when CI completes using the background command pattern.

### Background Command Pattern
In Claude Desktop / code assistant environments, launch the command with background execution enabled (`run_in_background: true` on the Bash / command execution tool) and end the turn immediately:

```bash
python "<skill-dir>/scripts/gh_helper.py" ci wait \
  --repo "<owner>/<repo>" \
  --sha <sha>
```

> [!NOTE]
> The `--sha` flag accepts both short prefix form (7+ characters, e.g. `724ef84`) and full 40-character commit hashes. Short SHAs resolve locally via `git rev-parse` when inside the repository checkout, or dynamically against recent workflow runs.
>
> If waiting by `--branch`, the command automatically ignores stale runs created more than 60s before invocation (unless `--include-existing` is explicitly passed). Therefore, `--sha <sha>` or `--run-id <id>` is always preferred after a push.

When the background process completes, the environment wakes the chat with the exit code and process output (the CI summary line and failure digest).

### Key Characteristics & Economics
- **Zero Token Cost While Waiting**: Polling happens entirely within the local Python process. Waiting incurs **0 model tokens**.
- **One Turn on Completion**: The model is only woken once the run finishes, consuming exactly **1 model turn** to inspect results and continue work.
- **Quiet Execution**: The command prints nothing to stdout while polling (no screen redraw floods). In the event of persistent GitHub connectivity failures, a single warning line is emitted to stderr after 10 minutes of continuous outage.
- **App Restarts**: If the client application or chat session restarts while a wait is in progress, background processes are terminated. The chat must re-issue the `ci wait` command upon resuming if the run is still in progress.

### Exit Codes

| Code | Meaning | Details |
|---|---|---|
| **0** | Success | All matching CI workflow runs completed successfully. |
| **1** | Failure / Cancelled | One or more runs completed with `failure`, `cancelled`, or `timed_out`. The output includes failing test digests. |
| **2** | Usage / Tool Missing | Invalid CLI arguments, target not specified, or `gh` CLI not installed/found in `PATH`. |
| **5** | Run Never Appeared | No matching workflow run was found for the given `--sha` or `--branch` within `--appear-timeout` seconds (default 180s). |
| **6** | Max-Wait Reached | The `--max-wait` limit elapsed before the workflow run completed. The agent should restart `ci wait`. |


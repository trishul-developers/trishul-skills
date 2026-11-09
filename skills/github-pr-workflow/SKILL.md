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

### 5. Waiting for CI Workflow Completion (`ci wait`)
```bash
python "skills/github-pr-workflow/scripts/gh_helper.py" ci wait \
  --repo "tosumitdhaka/trishul-tactical-engine" \
  --sha 95ea658
```
Or by workflow run ID:
```bash
python "skills/github-pr-workflow/scripts/gh_helper.py" ci wait \
  --repo "tosumitdhaka/trishul-tactical-engine" \
  --run-id 42575624916 \
  --interval 15
```

---

## Waking a chat when CI finishes (ci wait)

When an orchestrator or worker agent pushes commits to GitHub, CI starts asynchronously. Rather than sitting idle or burning model turns on active polling, agents can wake themselves up automatically when CI completes using the background command pattern.

### Background Command Pattern
In Claude Desktop / code assistant environments, launch the command with background execution enabled (`run_in_background: true` on the Bash / command execution tool) and end the turn immediately:

```bash
python "C:\Users\tosum\.claude\skills\github-pr-workflow\scripts\gh_helper.py" ci wait \
  --repo tosumitdhaka/trishul-tactical-engine \
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

### Parallel Operation with `hub_wait`
`ci wait` operates independently of and seamlessly alongside `hub_wait` (from the `hub-messenger` skill). A multi-agent coordinator can run both background tasks simultaneously:
- `hub_wait` waits quietly for inbound agent mail / task handoffs.
- `ci wait` waits quietly for remote GitHub Actions workflow completion.

Whichever event completes first wakes the agent to take immediate action.

### Exit Codes

| Code | Meaning | Details |
|---|---|---|
| **0** | Success | All matching CI workflow runs completed successfully. |
| **1** | Failure / Cancelled | One or more runs completed with `failure`, `cancelled`, or `timed_out`. The output includes failing test digests. |
| **2** | Usage / Tool Missing | Invalid CLI arguments, target not specified, or `gh` CLI not installed/found in `PATH`. |
| **5** | Run Never Appeared | No matching workflow run was found for the given `--sha` or `--branch` within `--appear-timeout` seconds (default 180s). |
| **6** | Max-Wait Reached | The `--max-wait` limit elapsed before the workflow run completed. The agent should restart `ci wait`. |


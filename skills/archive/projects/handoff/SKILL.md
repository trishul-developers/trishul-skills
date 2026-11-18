---
name: handoff
description: Check and act on file handoffs in trishul-agent-hub. Use when asked to check handoffs, or on the 15-minute cron check, to pick up any package whose next_owner is antigravity.
---

# Handoff Check (Antigravity Orchestrator)

1. Read `handoff/README.md` in `E:\Projects\trishul-agent-hub\.claude\worktrees\trishul-agent-orchestrator-950990\handoff\README.md` (or `orchestrator-main\handoff\README.md`).
2. List all `handoff/*.md` (except `README.md`).
3. For each file with `next_owner: antigravity`:
   - Follow the README rules.
   - As Orchestrator, spawn bounded implementor subagents to implement the requested package steps in the worktree and branch specified. Do not implement complex code directly in the orchestrator session.
   - Verify all checks in WSL:
     `export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/trishul-agent-hub"; uv sync; uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`
     (and slow tests if required).
   - Once implementation and checks are green, record the commit SHA in the worktree.
   - Update the handoff file:
     - set `sha: <commit>`
     - set `status: handoff`
     - set `next_owner: codex` (or reviewer specified in the handoff)
     - set `updated: <YYYY-MM-DD HH:MM>`
     - append the handoff block under `## Handoff`
     - append a log entry under `## Log`: `<updated> antigravity: <summary of handoff>`
   - Commit the handoff file change in the orchestrator worktree with message:
     `handoff: <package> → codex`
   - **Wake/Resume Codex Orchestrator Session**: Immediately execute the following PowerShell command:
     ```powershell
     codex exec resume 01a18564-9bf3-7061-80a3-6a5969effa10 `
       "Antigravity has handed back a package. Read the handoff files and act only on an unconsumed handoff assigned to Claude, Sonnet, Codex, or the orchestrator. Follow the project's review and gate process."
     ```
4. If `next_owner` is not `antigravity`, do nothing.

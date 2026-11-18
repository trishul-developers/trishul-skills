---
name: opencode-headless
description: Execute OpenCode non-interactively via `opencode run` with granular control over models (provider/model#variant), reasoning effort (low, medium, high, max), permission auto-approval (--auto), thinking blocks, git worktree isolation, session continuation/forking, and structured telemetry.
compatibility: Requires OpenCode CLI (opencode) on PATH or installed. Tested on Windows/WSL with OpenCode 2.2+.
tags: [opencode, headless, cli, execution, multi-agent, automation, reasoning-effort]
---

# OpenCode Headless CLI Runner

This skill provides an automated, non-interactive execution harness for OpenCode via its CLI command (`opencode run`). It manages model selection across providers, granular reasoning effort / variant control, session continuity, permission auto-approvals, git worktree isolation, prompt length safety, timeout supervision, and structured execution telemetry.

## Core Capabilities
- **Model Selection & Reasoning Effort**:
  - Direct provider and model specification: `--model <provider/model>` (e.g. `anthropic/claude-3-7-sonnet`, `openai/o3-mini`, `google/gemini-2.5-pro`).
  - Granular reasoning effort / variant control: `--effort <low|medium|high|max>`, automatically mapped to OpenCode's native `#variant` syntax (e.g. `openai/o3-mini#high`).
  - Native inline format support: pass `--model provider/model#variant` directly.
- **Autonomous Execution & Permissions**:
  - `--auto`: Auto-approves tool execution and shell actions not explicitly forbidden.
  - `--archived`: Automatically keeps automated/scripted runs archived so they do not pollute active session lists.
- **Thinking Blocks**:
  - `--thinking`: Toggles or exposes model reasoning and thinking traces in output streams.
- **Session Continuity & Isolation**:
  - Session continuation: `--continue` (latest session) or `--session <SESSION_ID>`.
  - Session branching: `--fork` to branch from an existing session without mutating it.
  - Git worktree isolation: `--worktree [NAME]` to run the task in an isolated branch/worktree.
- **Context Injection**:
  - Attach files directly into the prompt context via repeatable `-f, --file <PATH>`.
  - Feed large task briefs via `--prompt-file <FILE>` or piped stdin (`-`).
- **Windows CLI Safety & Process Management**:
  - Detects briefs exceeding Windows command-line bounds (>16k chars) and safely passes them via file attachment.
  - Process tree cleanup on timeout (`taskkill /PID /T /F` on Windows; process group termination on Unix).
- **Execution Telemetry**:
  - Automatically captures `prompt.md`, `stdout.txt` (or `stdout.json`), `stderr.log`, and `result.json` in a timestamped run directory.

## Quickstart Recipes

### 1. High-Effort Reasoning Task
```bash
python "scripts/opencode_headless.py" \
  -m openai/o3-mini \
  -e high \
  -C "<repo_dir>" \
  "Analyze this algorithm for race conditions and propose a thread-safe refactor."
```

### 2. Multi-Provider Model Delegation with Thinking Traces
```bash
python "scripts/opencode_headless.py" \
  -m anthropic/claude-3-7-sonnet \
  -e high \
  --thinking \
  -C "<repo_dir>" \
  "Design a high-throughput event processing pipeline with backpressure."
```

### 3. Implementation Brief via Prompt File in an Isolated Git Worktree
```bash
python "scripts/opencode_headless.py" \
  -m anthropic/claude-3-7-sonnet \
  -e medium \
  --worktree feature-auth-refactor \
  --prompt-file "briefs/phase-02-auth.md" \
  -C "<repo_dir>" \
  --timeout 1800
```

### 4. Structured JSON Output for Scripts and CI
```bash
python "scripts/opencode_headless.py" \
  -m openai/gpt-4o \
  --format json \
  -C "<repo_dir>" \
  "Inspect package.json and output security recommendations."
```

### 5. Resuming or Continuing a Previous Session
```bash
python "scripts/opencode_headless.py" \
  --session "0194e3a2-7b4c-7c01-8e99-823a0df4b5cd" \
  "Now write unit tests covering the newly added methods."
```

### 6. Dry-Run Verification (0 Quota Spent)
```bash
python "scripts/opencode_headless.py" \
  -m openai/o3-mini -e high --dry-run "Test verification"
```

## Telemetry and Artifacts
Every execution writes to a timestamped directory under `%TEMP%/opencode-headless-runs/<stamp>-<id>/` (or custom `--out-dir`):
- `prompt.md`: Exact prompt provided.
- `stdout.txt` / `stdout.json`: Primary output captured from OpenCode.
- `stderr.log`: Complete stderr diagnostics.
- `result.json`: Execution metadata including `run_id`, `status`, `duration_seconds`, `exit_code`, `model`, `effort`, and artifact paths.

---
name: claude-headless
description: Execute Anthropic Claude Code non-interactively via print mode (`claude -p`) with fine-grained control over models (claude-sonnet-5-5, claude-opus-5-5, claude-haiku-5-5), reasoning effort (--effort), tool whitelisting (--allowed-tools, --tools), permission skipping, system prompt overrides, output formatting (json, text), minimal execution mode (--bare), and session continuity.
compatibility: Requires Claude Code CLI (claude) on PATH and authenticated. Tested on Windows with Claude Code 2.x+.
tags: [claude, anthropic, headless, cli, execution, multi-agent, automation]
---

# Claude Headless CLI Runner

This skill provides an automated execution harness for Anthropic's Claude Code CLI using non-interactive print mode (`claude -p`). It handles stdin decoupling (preventing the 3-second stdin wait timeout), Windows >16k CLI length safety (piping long prompts via stdin), `--` separator safety for variadic flags, system prompt injection, allowed tool constraints, output parsing, and lifecycle termination.

## Core Capabilities
- **Model Selection**: Switch between Claude reasoning tiers (`claude-sonnet-5-5`, `claude-opus-5-5`, `claude-haiku-5-5`).
- **Reasoning Effort**: Control effort with `-e, --effort` (`low`, `medium`, `high`, `xhigh`, `max`).
- **Tool Permitting**:
  - Restrict execution to safe tools via `--allowed-tools "Read,Edit,Bash(git *)"` or `--tools "Read,Edit,Bash"`.
  - Full unattended automation via `--dangerously-skip-permissions`.
- **Context Injection**:
  - Pass prompts inline, via `--prompt-file <FILE>`, or `-` for stdin.
  - Set working directory with `-C, --cd <DIR>` and extra directories with `--add-dir <DIR>`.
  - Replace or append system prompts via `--system-prompt` / `--append-system-prompt` (or `*-file`).
  - Enforce structured JSON output via `--json-schema <SCHEMA>`.
  - Minimal mode `--bare` (skips hooks, LSP, auto-memory). **OAuth caveat**: `--bare` ignores OAuth/keychain auth outside cloud/background sessions and requires `ANTHROPIC_API_KEY` in the environment.
- **Output Formats**:
  - `json`: Returns structured payload containing execution result, session id, and tokens.
  - `text`: Direct output string.
  - `stream-json`: Real-time streaming chunks.
- **Session Continuity**: Resume past conversations via `--resume <SESSION_ID>` or `--continue`.
- **Process Cleanliness**: Automatic recursive process tree destruction on timeout (`taskkill /PID /T /F` on Windows).

## Quickstart Recipes

### 1. Basic Fast Architectural Query (Haiku)
```bash
python "<skill-dir>/scripts/claude_headless.py" \
  -m claude-haiku-5-5 \
  -e low \
  -C "<repo_dir>" \
  "Summarize the relationship between EntityRegistry and CombatManager."
```

### 2. Implementation Brief with Whitelisted Tools
```bash
python "<skill-dir>/scripts/claude_headless.py" \
  -m claude-sonnet-5-5 \
  -e high \
  --allowed-tools "Read,Edit,Bash(git status),Bash(git diff)" \
  --dangerously-skip-permissions \
  -C "<repo_dir>" \
  --prompt-file "briefs/patch-comms-channel.md" \
  --timeout 1800
```

### 3. Review / Audit with System Prompt & JSON Schema
```bash
python "<skill-dir>/scripts/claude_headless.py" \
  -m claude-opus-5-5 \
  --tools "Read,Grep,Glob" \
  --system-prompt "You are a strict security and determinism auditor." \
  --output-format json \
  --json-schema '{"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"]}' \
  --prompt-file "briefs/review-combat-tick.md"
```

### 4. Resuming an Ongoing Session
```bash
python "<skill-dir>/scripts/claude_headless.py" \
  --resume "01efca8c-0342-4efb-8af4-61632e4afa01" \
  "Proceed with batch 2 implementation and report diff."
```

### 5. Dry-Run Verification (0 Quota Spent)
```bash
python "<skill-dir>/scripts/claude_headless.py" \
  -m claude-sonnet-5-5 --dangerously-skip-permissions --dry-run "Test dry run"
```

## Telemetry and Artifacts
Every run writes into `%TEMP%/claude-headless-runs/<stamp>-<id>/`:
- `prompt.md`: Exact submitted prompt.
- `response.md`: Output response text.
- `stdout.json` / `stdout.txt`: Raw CLI stdout.
- `stderr.log`: Raw CLI stderr.
- `result.json`: Execution metadata including `session_id`, `status`, `effort`, `duration_seconds`, and `exit_code`.

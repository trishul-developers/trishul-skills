---
name: agy-headless
description: Execute Google Antigravity (agy) non-interactively via print mode (`agy -p`) with granular control over models (gemini-3.8-flash, claude-sonnet-4-6, claude-opus-4-6-thinking, gpt-oss-120b-medium), reasoning effort (low, medium, high, xhigh, max), execution modes (auto, accept-edits, plan), permission auto-approval, output formatting (json, text, stream-json), structured schema validation, Windows command line length safety, and conversation resumption.
compatibility: Requires Antigravity CLI (agy) on PATH and signed in. Tested on Windows with agy 1.4.12+.
tags: [antigravity, agy, gemini, headless, cli, execution, multi-agent, automation]
---

# Antigravity (agy) Headless CLI Runner

This skill provides an industrial-grade, non-interactive execution wrapper around Google Antigravity (`agy`). It enables automated sub-task delegation, batch code generation, structured audits, and background execution without terminal hangs or prompt truncation.

## Core Capabilities
- **Model Flexibility**: Select models dynamically:
  - `gemini-3.8-flash`: Fast, efficient, tiered effort (`low`, `medium`, `high`, `xhigh`, `max`).
  - `claude-sonnet-4-6` / `claude-opus-4-6-thinking`: Deep reasoning Claude models hosted on AGY.
  - `gpt-oss-120b-medium`: High-capability open-weight weights.
- **Execution Modes**:
  - `auto`: Standard agentic execution.
  - `accept-edits`: Directly applies proposed code diffs.
  - `plan`: High-level multi-step planning without tool side effects.
- **Windows Command-Line Safety**: Automatically detects briefs exceeding Windows CLI limits (~16k chars), writes them safely to disk, and instructs the agent to read the prompt file.
- **Output Formats**:
  - `json`: Returns structured metadata including turn count, model status, and token usage.
  - `text`: Plain text output stream.
  - `stream-json`: Line-delimited event streams.
- **Permission Management**:
  - Default: Safe file operations.
  - `--auto-approve`: Passes `--dangerously-skip-permissions` for unattended shell/compiler executions.
- **Session Continuity**: Resume past conversations via `--resume <CONVERSATION_ID>` or `--continue`.

## Quickstart Recipes

### 1. Basic Fast Query (Gemini Flash Low-Effort)
```bash
python "E:/Projects/Skills/skills/headless/agy-headless/scripts/agy_headless.py" \
  -m gemini-3.8-flash \
  -e low \
  -C "E:/Projects/trishul-tactical-engine" \
  "Summarize the assembly definition files in Assets/Scripts."
```

### 2. Implementation with Auto-Approval
```bash
python "E:/Projects/Skills/skills/headless/agy-headless/scripts/agy_headless.py" \
  -m gemini-3.8-flash \
  -e high \
  --mode auto \
  --auto-approve \
  -C "E:/Projects/trishul-tactical-engine" \
  --prompt-file "briefs/generate-air-component.md" \
  --timeout 1800
```

### 3. Enforcing JSON Schema
```bash
python "E:/Projects/Skills/skills/headless/agy-headless/scripts/agy_headless.py" \
  -m gemini-3.8-flash \
  -e medium \
  --output-format json \
  --json-schema "schemas/code-audit-schema.json" \
  --prompt-file "briefs/inspect-logs.md"
```

### 4. Continuing an Existing Conversation
```bash
python "E:/Projects/Skills/skills/headless/agy-headless/scripts/agy_headless.py" \
  --resume "3ec975ab-8238-4a51-aeec-9e6831bb5ec5" \
  "Now apply the suggested fix to the damaged component script."
```

### 5. Dry-Run Verification (0 Quota Spent)
```bash
python "E:/Projects/Skills/skills/headless/agy-headless/scripts/agy_headless.py" \
  -m gemini-3.8-flash -e high --auto-approve --dry-run "Test dry run"
```

## Telemetry and Artifacts
Every run records artifacts under `%TEMP%/agy-headless-runs/<stamp>-<id>/`:
- `prompt.md`: Exact prompt submitted.
- `response.md`: Antigravity's final text response.
- `stdout.json` / `stdout.txt`: Raw CLI stdout.
- `stderr.log`: Raw CLI stderr.
- `agy.log`: Native agy diagnostic log file (`--log-file`).
- `result.json`: Execution metadata including `conversation_id`, `status`, `duration_seconds`, `exit_code`, and `usage`.

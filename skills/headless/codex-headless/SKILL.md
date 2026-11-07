---
name: codex-headless
description: Execute OpenAI Codex non-interactively via `codex exec` with precise control over model (gpt-6.1-sol, gpt-6.1-terra, gpt-6-astra, gpt-6-luna), reasoning effort (low, medium, high, xhigh, max, ultra), sandbox permissions (read-only, workspace-write, danger-full-access), structured JSON output schemas, directory context, git worktrees, image inputs, and thread resumption.
compatibility: Requires codex CLI on PATH and signed in. Tested on Windows with codex-cli 0.166.0+.
tags: [codex, headless, cli, execution, multi-agent, automation]
---

# Codex Headless CLI Runner

This skill provides a programmatic, non-interactive execution harness for OpenAI Codex using `codex exec`. It solves command-line quoting, stdin streaming, process lifecycle supervision, timeout management, structured output schemas, and multi-agent thread resumption.

## Core Capabilities
- **Model Selection**: Run any tier-1 or lightweight Codex model (`gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-6-astra`, `gpt-6-luna`).
- **Reasoning Effort Control**: Fine-tune depth (`low`, `medium`, `high`, `xhigh`, `max`, `ultra`).
- **Sandbox Isolation**:
  - `read-only`: Code reviews, queries, and static inspections without file modifications.
  - `workspace-write` (default): Edits within the target project directory.
  - `danger-full-access`: Requires `--allow-full-access` flag.
- **Context Injection**:
  - Multi-directory write access via `--add-dir <DIR>`.
  - Automatic isolation in a managed Git worktree via `--worktree`.
  - Multimodal input via repeatable `--image <PATH>`.
  - Output contract enforcement via `--output-schema <SCHEMA_FILE>`.
- **Session Continuity**: Resume or fork existing threads using `--resume <THREAD_ID>` or `--fork <THREAD_ID>`.
- **Fault Tolerance**: Automatic recursive process tree cleanup on timeout (`taskkill /PID /T /F` on Windows) to prevent orphaned language servers or compile workers.

## Quickstart Recipes

### 1. Basic Read-Only Query / Code Review
```bash
python "E:/Projects/Skills/skills/headless/codex-headless/scripts/codex_headless.py" \
  -m gpt-6.1-sol \
  -e high \
  -s read-only \
  -C "E:/Projects/trishul-tactical-engine" \
  "Review Assets/Scripts/Combat/CombatManager.cs for allocation hot-spots and list top 3 issues."
```

### 2. Large Implementation Brief via Prompt File
```bash
python "E:/Projects/Skills/skills/headless/codex-headless/scripts/codex_headless.py" \
  -m gpt-6.1-sol \
  -e high \
  -s workspace-write \
  -C "E:/Projects/trishul-tactical-engine" \
  --prompt-file "briefs/phase-spec-step-04.md" \
  --timeout 1800
```

### 3. Enforcing Structured JSON Output Schema
```bash
python "E:/Projects/Skills/skills/headless/codex-headless/scripts/codex_headless.py" \
  -m gpt-6.1-terra \
  -e medium \
  -s read-only \
  --output-schema "schemas/audit-report.json" \
  --prompt-file "briefs/audit-request.md"
```

### 4. Resuming an Existing Thread
```bash
python "E:/Projects/Skills/skills/headless/codex-headless/scripts/codex_headless.py" \
  --resume "01a1a10e-d6b3-7673-aa39-442645d464eb" \
  "Now implement the second test case and run the compilation check."
```

### 5. Dry-Run Verification (0 Quota Spent)
```bash
python "E:/Projects/Skills/skills/headless/codex-headless/scripts/codex_headless.py" \
  -m gpt-6.1-sol -e ultra --worktree --dry-run "Test prompt"
```

## Telemetry and Artifacts
Every run writes to a timestamped folder under `%TEMP%/codex-headless-runs/<stamp>-<id>/` (or `--out-dir`):
- `prompt.md`: Exact prompt sent.
- `last_message.md`: Codex's final response text.
- `events.jsonl`: Raw stream of JSON events emitted by `codex exec --json`.
- `stderr.log`: Complete stderr log.
- `result.json`: Execution metadata including `thread_id`, `status`, `duration_seconds`, `exit_code`, and token `usage`.

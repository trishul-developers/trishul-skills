# Universal Headless CLI Execution Playbook

This guide details how to programmatically invoke OpenAI Codex, Google Antigravity (AGY, native or WSL), and Anthropic Claude Code non-interactively using the production-grade runners located in `skills/`.

---

## 1. Executive Summary

| Provider | Headless CLI Subcommand | Runner Script Path | Default Model | Primary Strengths |
|---|---|---|---|---|
| **OpenAI Codex** | `codex exec` | `skills/codex-headless/scripts/codex_headless.py` | `gpt-6.2-sol` | Complex algorithms, deterministic simulation, deep math |
| **Google Antigravity** | `agy -p` | `skills/agy-headless/scripts/agy_headless.py` | `gemini-3.8-flash-medium` | High-speed execution, low quota cost, Unity automation |
| **Antigravity (WSL)** | `wsl -e bash -l -s` → `agy -p` | `skills/agy-wsl-headless/scripts/agy_wsl_headless.py` | *(uses `agy` default)* | WSL execution and native `swarm` orchestration |
| **Anthropic Claude** | `claude -p` | `skills/claude-headless/scripts/claude_headless.py` | `claude-sonnet-5-5` | Architecture design, PR reviews, project management |

> **Cross-agent rule:** Deploy headless runners only to *other* agents (e.g. Claude receives `agy-headless` + `codex-headless`, Codex receives `agy-headless` + `claude-headless`, Antigravity receives `claude-headless` + `codex-headless`).

---

## 2. Common CLI Invariants & Edge Cases

### A. Windows Command Line Length Safety
Windows imposes a limit (~32,767 characters) on process command lines. Passing extensive task briefs (e.g. 50k character specs) directly in inline arguments will cause subprocess launch failures or silent truncation.
- **Solution**:
  - `codex_headless.py` and `claude_headless.py` (>16k chars) pipe the prompt via `stdin`.
  - `agy_headless.py` (>16k chars) writes the prompt to `prompt.md`, adds `--add-dir <run_dir>`, and instructs the agent to read the prompt file.
  - `agy_wsl_headless.py` always writes `prompt.md` and reads it inside WSL (`PROMPT_TEXT=$(cat ...)`).

### B. Decoupled Stdin
Claude Code (`claude -p`) polls stdin for 3 seconds if not redirected, printing:
```
Warning: no stdin data received in 3s, proceeding without it.
```
- **Solution**: `claude_headless.py` directs `stdin=subprocess.DEVNULL` for short prompts (≤16k chars), eliminating unnecessary latency, and uses `--` before the positional prompt so variadic flags (`--allowed-tools`, `--tools`, `--add-dir`) never swallow it.

### C. Clean Process Tree Termination
On Windows, standard `proc.kill()` terminates only the parent shell, leaving compiler workers, Node.js background daemons, or Python test runners orphaned in background processes.
- **Solution**: All runners execute `taskkill /PID <pid> /T /F` on Windows (and `os.killpg` on POSIX) when a timeout expires, and `agy_wsl_headless.py` also wraps `agy` in Linux `timeout -k 10s` inside `dispatch.sh`.

---

## 3. Codex Headless Runner (`codex_headless.py`)

### Parameter Matrix
```bash
python skills/codex-headless/scripts/codex_headless.py [OPTIONS] [PROMPT]
```

- `--prompt-file`: Path to prompt file (alternative to positional `PROMPT` or `-` for stdin).
- `-m, --model`: `gpt-6.2-sol`, `gpt-6.1-terra`, `gpt-6.2-astra`, `gpt-6-luna`.
- `-e, --effort`: `low`, `medium`, `high`, `xhigh`, `max`, `ultra`.
- `-s, --sandbox`:
  - `read-only`: Queries, inspections, reviews (no file changes).
  - `workspace-write`: Default. Writes restricted to project folder.
  - `danger-full-access`: Requires `--allow-full-access`.
- `-C, --cd, --cwd`: Working root directory.
- `--add-dir`: Additional writable paths (repeatable).
- `--worktree`: Isolates run in a newly spawned git worktree.
- `-c, --config`: Configuration override `key=value` (repeatable).
- `-i, --image`: Image file path to attach (repeatable).
- `--output-schema`: Path to a JSON schema file enforcing structured model output.
- `--resume <THREAD_ID>` / `--fork <THREAD_ID>`: Resumes or forks prior thread.
- `--ephemeral`: Run without persisting thread to local disk.
- `--timeout`: Timeout in seconds (default: 1800).
- `--out-dir`: Explicit directory to save run artifacts.
- `--dry-run`: Prints exact command without invoking Codex.

### Example: Running a Hard Architecture Refactor
```bash
python "skills/codex-headless/scripts/codex_headless.py" \
  -m gpt-6.2-sol \
  -e high \
  -s workspace-write \
  -C "<repo_dir>" \
  --prompt-file "briefs/refactor-spatial-partitioning.md"
```

---

## 4. Antigravity Headless Runner (`agy_headless.py`)

### Parameter Matrix
```bash
python skills/agy-headless/scripts/agy_headless.py [OPTIONS] [PROMPT]
```

- `--prompt-file`: Path to prompt file.
- `-m, --model`: `gemini-3.8-flash-medium` (default), `gemini-4-argon-medium`, `gemini-4-hydrogen-high`, `claude-sonnet-5-5`, `claude-opus-5-5`.
- `-e, --effort`: `low`, `medium`, `high`, `xhigh`, `max`.
- `--mode`: `auto`, `accept-edits`, `plan`.
- `--output-format`: `json` (default), `text`, `stream-json`.
- `--auto-approve`: Passes `--dangerously-skip-permissions` for unattended automation.
- `--print-timeout`: Duration passed to `agy --print-timeout` (e.g. `60s`, `300s`, `0s`).
- `--disable-slash-commands`: Disable slash command and skill expansion in print mode.
- `--json-schema`: Enforces structured JSON schema (file path or inline JSON).
- `-C, --cd, --cwd`: Working root directory.
- `--add-dir`: Additional workspace directory (repeatable).
- `--resume <CONVERSATION_ID>`: Resumes past conversation.
- `-c, --continue`: Continues most recent conversation.
- `--timeout`: Seconds before termination (default: 1800).
- `--out-dir`: Explicit directory to save run artifacts.
- `--dry-run`: Preview command without spending quota.

### Example: Batch Log Analysis (Fast & Cheap)
```bash
python "skills/agy-headless/scripts/agy_headless.py" \
  -m gemini-3.8-flash-medium \
  -e low \
  --output-format json \
  -C "<repo_dir>" \
  "Inspect Editor.log and extract all unhandled NullReferenceExceptions."
```

---

## 5. Antigravity WSL Headless & Swarm Runner (`agy_wsl_headless.py`)

### Parameter Matrix
```bash
python skills/agy-wsl-headless/scripts/agy_wsl_headless.py [OPTIONS] [PROMPT]
```

- `--prompt-file`: Path to prompt file.
- `-m, --model`: Antigravity model name (optional; uses `agy` default if omitted).
- `-e, --effort`: `low`, `medium`, `high`, `xhigh`, `max`.
- `--mode`: `accept-edits`, `auto`, `plan`.
- `--output-format`: `text`, `json`, `stream-json`.
- `--json-schema`: Path to JSON schema file (translated to WSL path) or inline `{...}` schema.
- `--auto-approve`: Pass `--dangerously-skip-permissions`.
- `--swarm`: Swarm mode (implies `--auto-approve` and defaults `--print-timeout` to `300s`).
- `--print-timeout`: Duration passed to `agy --print-timeout`.
- `-C, --cd`: Working directory (Windows, WSL UNC, or POSIX path; validated on Windows).
- `--add-dir`: Additional writable directory (repeatable).
- `--resume <CONVERSATION_ID>` / `-c, --continue`: Resume or continue conversation.
- `--wsl-distro` / `--agy-bin`: Override WSL distribution or `agy` binary path.
- `--timeout`: Outer subprocess & Linux `timeout` wrapper limit in seconds (default: 1800).
- `--out-dir` / `--no-env-note` / `--dry-run`: Output directory, skip Windows-mount note, or preview `dispatch.sh`.

### Example: Headless Swarm Orchestration
```bash
python "skills/agy-wsl-headless/scripts/agy_wsl_headless.py" \
  --swarm \
  --print-timeout 180s \
  -C "<repo_dir>" \
  --prompt-file "briefs/swarm-task.md"
```

---

## 6. Claude Headless Runner (`claude_headless.py`)

### Parameter Matrix
```bash
python skills/claude-headless/scripts/claude_headless.py [OPTIONS] [PROMPT]
```

- `--prompt-file`: Path to prompt file.
- `-m, --model`: `claude-sonnet-5-5` (default), `claude-opus-5-5`, `claude-haiku-5-5`.
- `-e, --effort`: `low`, `medium`, `high`, `xhigh`, `max`.
- `--output-format`: `json` (default), `text`, `stream-json`.
- `--allowed-tools`: Whitelist tools (e.g. `"Read,Edit,Bash(git *)"`).
- `--tools`: List of available tools or `'default'`.
- `--dangerously-skip-permissions`: Bypass all tool approval prompts.
- `--system-prompt` / `--system-prompt-file`: System prompt override.
- `--append-system-prompt` / `--append-system-prompt-file`: Append to default system prompt.
- `-C, --cd, --cwd`: Working directory root.
- `--add-dir`: Additional directories to allow tool access.
- `--bare`: Minimal execution mode (skips hooks, auto-memory, LSP indexing; requires `ANTHROPIC_API_KEY` since OAuth/keychain auth is skipped).
- `--json-schema`: JSON schema to enforce output structure.
- `--resume <SESSION_ID>` / `-c, --continue`: Continue existing session.
- `--timeout`: Timeout in seconds (default: 1800).
- `--out-dir`: Explicit directory to save run artifacts.
- `--dry-run`: Inspect command without launching Claude.

### Example: Independent Checkpoint Review
```bash
python "skills/claude-headless/scripts/claude_headless.py" \
  -m claude-sonnet-5-5 \
  -e high \
  --allowed-tools "Read,Bash(git diff),Bash(git log)" \
  --dangerously-skip-permissions \
  -C "<repo_dir>" \
  --prompt-file "briefs/checkpoint-g02-review.md"
```

---

## 7. Execution Telemetry (`result.json`)

All runners produce a standardized `result.json` in their run directory:
```json
{
  "status": "success",
  "exit_code": 0,
  "model": "gpt-6.2-sol",
  "effort": "high",
  "duration_seconds": 14.2,
  "thread_id": "01a1a10e-d6b3-7673-aa39-442645d464eb",
  "run_dir": "<TEMP>/codex-headless-runs/20261107-133003-047925",
  "usage": {
    "prompt_tokens": 1420,
    "completion_tokens": 380,
    "total_tokens": 1800
  }
}
```

# Universal Headless CLI Execution Playbook

This guide details how to programmatically invoke OpenAI Codex, Google Antigravity (AGY), and Anthropic Claude Code non-interactively using the production-grade runners located in `skills/`.

---

## 1. Executive Summary

| Provider | Headless CLI Subcommand | Runner Script Path | Default Model | Primary Strengths |
|---|---|---|---|---|
| **OpenAI Codex** | `codex exec` | `skills/codex-headless/scripts/codex_headless.py` | `gpt-6.1-sol` | Complex algorithms, deterministic simulation, deep math |
| **Google Antigravity** | `agy -p` | `skills/agy-headless/scripts/agy_headless.py` | `gemini-3.8-flash` | High-speed execution, low quota cost, Unity automation |
| **Anthropic Claude** | `claude -p` | `skills/claude-headless/scripts/claude_headless.py` | `claude-3-7-sonnet` | Architecture design, PR reviews, project management |

---

## 2. Common CLI Invariants & Edge Cases

### A. Windows Command Line Length Safety
Windows imposes a limit (~32,767 characters) on process command lines. Passing extensive task briefs (e.g. 50k character specs) directly in inline arguments will cause subprocess launch failures or silent truncation.
- **Solution**: The headless runners automatically detect briefs exceeding 16k characters, persist them to a timestamped `prompt.md` in the run directory, and instruct the agent to read the prompt file.

### B. Decoupled Stdin
Claude Code (`claude -p`) polls stdin for 3 seconds if not redirected, printing:
```
Warning: no stdin data received in 3s, proceeding without it.
```
- **Solution**: `claude_headless.py` explicitly directs `stdin=subprocess.DEVNULL` (unless stdin piping is intentionally requested with `-`), eliminating unnecessary latency.

### C. Clean Process Tree Termination
On Windows, standard `proc.kill()` terminates only the parent shell, leaving compiler workers, Node.js background daemons, or Python test runners orphaned in background processes.
- **Solution**: All three runners execute `taskkill /PID <pid> /T /F` on Windows when a timeout expires, guaranteeing zero orphaned background processes.

---

## 3. Codex Headless Runner (`codex_headless.py`)

### Parameter Matrix
```bash
python skills/codex-headless/scripts/codex_headless.py [OPTIONS] [PROMPT]
```

- `-m, --model`: `gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-6-astra`, `gpt-6-luna`.
- `-e, --effort`: `low`, `medium`, `high`, `xhigh`, `max`, `ultra`.
- `-s, --sandbox`:
  - `read-only`: Queries, inspections, reviews (no file changes).
  - `workspace-write`: Default. Writes restricted to project folder.
  - `danger-full-access`: Requires `--allow-full-access`.
- `-C, --cd`: Working root directory.
- `--add-dir`: Additional writable paths.
- `--worktree`: Isolates run in a newly spawned git worktree.
- `--output-schema`: Path to a JSON schema file enforcing structured model output.
- `--resume <THREAD_ID>`: Resumes prior thread.
- `--timeout`: Timeout in seconds (default: 1800).
- `--dry-run`: Prints exact command without invoking Codex.

### Example: Running a Hard C# Architecture Refactor
```bash
python "skills/codex-headless/scripts/codex_headless.py" \
  -m gpt-6.1-sol \
  -e high \
  -s workspace-write \
  -C "E:/Projects/trishul-tactical-engine" \
  --prompt-file "briefs/refactor-spatial-partitioning.md"
```

---

## 4. Antigravity Headless Runner (`agy_headless.py`)

### Parameter Matrix
```bash
python skills/agy-headless/scripts/agy_headless.py [OPTIONS] [PROMPT]
```

- `-m, --model`: `gemini-3.8-flash`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`, `gpt-oss-120b-medium`.
- `-e, --effort`: `low`, `medium`, `high`, `xhigh`, `max`.
- `--mode`: `auto`, `accept-edits`, `plan`.
- `--output-format`: `json` (default), `text`, `stream-json`.
- `--auto-approve`: Passes `--dangerously-skip-permissions` for unattended automation.
- `--json-schema`: Enforces structured JSON schema.
- `--resume <CONVERSATION_ID>`: Resumes past conversation.
- `-c, --continue`: Continues most recent conversation.
- `--timeout`: Seconds before termination (default: 1800).
- `--dry-run`: Preview command without spending quota.

### Example: Batch Unity Log Analysis (Fast & Cheap)
```bash
python "skills/agy-headless/scripts/agy_headless.py" \
  -m gemini-3.8-flash \
  -e low \
  --output-format json \
  -C "E:/Projects/trishul-tactical-engine" \
  "Inspect Editor.log and extract all unhandled C# NullReferenceExceptions."
```

---

## 5. Claude Headless Runner (`claude_headless.py`)

### Parameter Matrix
```bash
python skills/claude-headless/scripts/claude_headless.py [OPTIONS] [PROMPT]
```

- `-m, --model`: `claude-3-7-sonnet`, `claude-3-5-haiku`, `claude-3-opus`.
- `--output-format`: `json` (default), `text`, `stream-json`.
- `--allowed-tools`: Whitelist tools (e.g. `"Read,Edit,Bash(git *)"`).
- `--dangerously-skip-permissions`: Bypass all tool approval prompts.
- `--system-prompt` / `--system-prompt-file`: System prompt override.
- `--bare`: Minimal execution mode (skips hooks, auto-memory, LSP indexing).
- `--resume <SESSION_ID>`: Continue existing session.
- `--timeout`: Timeout in seconds (default: 1800).
- `--dry-run`: Inspect command without launching Claude.

### Example: Independent Checkpoint Review
```bash
python "skills/claude-headless/scripts/claude_headless.py" \
  -m claude-3-7-sonnet \
  --allowed-tools "Read,Bash(git diff),Bash(git log)" \
  --dangerously-skip-permissions \
  -C "E:/Projects/trishul-tactical-engine" \
  --prompt-file "briefs/checkpoint-g02-review.md"
```

---

## 6. Execution Telemetry (`result.json`)

All three runners produce a standardized `result.json` in their run directory:
```json
{
  "status": "success",
  "exit_code": 0,
  "model": "gpt-6.1-sol",
  "effort": "high",
  "duration_seconds": 14.2,
  "thread_id": "01a1a10e-d6b3-7673-aa39-442645d464eb",
  "run_dir": "C:\\Users\\tosum\\AppData\\Local\\Temp\\codex-headless-runs\\20261107-133003-047925",
  "usage": {
    "prompt_tokens": 1420,
    "completion_tokens": 380,
    "total_tokens": 1800
  }
}
```

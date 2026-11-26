---
name: agy-wsl-headless
description: Execute Google Antigravity (`agy -p`) inside WSL (Ubuntu) non-interactively from Windows or WSL, with built-in support for native `swarm` orchestration (`swarm`, `post_message`, `read_board`, `swarm_wait`), Windows-to-WSL path translation, quote-safe `bash -l -s` stdin dispatch, `--print-timeout`, `--dangerously-skip-permissions`, and telemetry (`result.json`).
compatibility: Requires WSL with Ubuntu and Antigravity CLI (`agy` 1.5.14+, e.g. `~/.local/bin/agy`) signed in.
tags: [antigravity, agy, wsl, headless, swarm, multi-agent, cli, automation]
---

# Antigravity WSL Headless & Swarm Runner (`agy-wsl-headless`)

Executes Google Antigravity (`agy -p`) inside WSL (Ubuntu) from Windows PowerShell or directly inside WSL, including multi-agent **native `swarm` orchestration**.

## Why a Dedicated WSL Runner?
1. **Quote-safe Windows → WSL dispatch**: Passing complex multi-line or swarm prompts through `wsl -e bash -lc '...'` from Windows PowerShell truncates or mangles nested quotes. `agy_wsl_headless.py` streams a generated script over `wsl -e bash -l -s` stdin and reads the prompt from a translated file, preserving every quote and newline.
2. **Automatic path translation**: Windows drive paths (`E:\Projects\...`) and WSL UNC paths (`\\wsl.localhost\<distro>\...`, `\\wsl$\<distro>\...`) passed to `-C`, `--prompt-file`, `--add-dir`, or `--json-schema` (when a file path) are automatically translated to POSIX WSL paths.
3. **Swarm-ready defaults**: In `agy` 1.5.14+, native swarm tools (`swarm`, `post_message`, `read_board`, `swarm_wait`) and builtin skills (`native_swarm`, `swarm_monitor`, `swarm_pane`, `swarm_narrator`) are built directly into `-p` headless sessions. Note that the read-only Swarm Aux Pane UI (`~/.gemini/antigravity-cli/builtin/plugins/swarm`) is skipped in headless mode while the full swarm runtime and board state run normally.

## Flags
- `prompt` / `--prompt-file <FILE>`: Task prompt inline, `-` for stdin, or file path.
- `-m, --model <MODEL>`: Antigravity model name (uses `agy` default if omitted).
- `-e, --effort <LEVEL>`: `low`, `medium`, `high`, `xhigh`, `max`.
- `--mode <MODE>`: `accept-edits`, `auto`, `plan`.
- `--output-format <FMT>`: `text`, `json`, `stream-json`.
- `--json-schema <PATH_OR_JSON>`: Path to JSON schema file or inline `{...}` JSON schema.
- `--auto-approve`: Pass `--dangerously-skip-permissions`.
- `--swarm`: Implies `--auto-approve` and defaults `--print-timeout` to `300s`.
- `--print-timeout <DUR>`: Duration passed to `agy --print-timeout` (e.g. `60s`, `300s`, `0s`).
- `-C, --cd <DIR>`: Working directory (Windows or WSL path; validated on Windows).
- `--add-dir <DIR>`: Additional writable directory (repeatable).
- `--resume <CONVERSATION_ID>` / `-c, --continue`: Resume or continue a conversation.
- `--wsl-distro <DISTRO>` / `--agy-bin <PATH>`: Override WSL distribution or `agy` binary path.
- `--timeout <SECONDS>`: Outer subprocess & Linux `timeout` wrapper limit (default: `1800`).
- `--out-dir <DIR>` / `--no-env-note` / `--dry-run`: Artifact output directory, skip Windows-mount note, or preview `dispatch.sh`.

## Practical Rules for Headless & Swarm Runs
- Always pass `--auto-approve` (`--dangerously-skip-permissions`) or `--swarm` so the coordinator and workers do not stall on interactive approval prompts.
- Set `--print-timeout` high enough for multi-turn worker coordination (e.g. `120s`, `600s`, or `0s` to wait until the turn finishes).
- Worktrees on Windows drives (`-C E:\...` or `/mnt/...`): the runner appends an environment note to the prompt (disable with `--no-env-note`). Native WSL `git` cannot read Windows worktrees (their gitdir paths are Windows paths), and WSL has no git-lfs or dotnet, so the worker is told to run `git.exe` and, if needed, `"/mnt/c/Program Files/dotnet/dotnet.exe"`, each with stdin redirected (`</dev/null`): Windows executables started from WSL wait for stdin EOF when it is an open pipe, and agy runs shell commands that way, so they hang for minutes otherwise. WSL configuration is never changed.
- Pass `--output-format json` to get `conversation_id` and `usage` in `result.json` (agent-delivery does this). The dispatch script and output are exchanged as UTF-8 bytes with LF line endings.
- On-disk swarm artifacts (`board.jsonl`, `members.json`, `swarm.json`) are written under `~/.gemini/antigravity-cli/brain/<conversation_id>/.system_generated/swarm/` inside WSL.

## Quickstart Recipes

### 1. Basic WSL Smoke Test
```bash
python "<skill-dir>/scripts/agy_wsl_headless.py" \
  --print-timeout 60s \
  "Reply with exactly: WSL_AGY_OK"
```

### 2. Headless Swarm Orchestration (`--swarm`)
`--swarm` automatically enables `--auto-approve` (`--dangerously-skip-permissions`) and sets a default `--print-timeout 300s` (override with `--print-timeout`).
```bash
python "<skill-dir>/scripts/agy_wsl_headless.py" \
  --swarm \
  --print-timeout 180s \
  -C "<repo_dir>" \
  --prompt-file "briefs/swarm-task.md"
```

### 3. Dry-Run Verification (0 Quota Spent)
```bash
python "<skill-dir>/scripts/agy_wsl_headless.py" \
  --swarm \
  -C "<repo_dir>" \
  --dry-run \
  "Test swarm dry run"
```

## Telemetry and Artifacts
Every run records artifacts under `%TEMP%/agy-wsl-headless-runs/<stamp>-<id>/` (or `--out-dir`):
- `prompt.md`: Exact prompt submitted.
- `dispatch.sh`: Exact bash script streamed to `wsl -e bash -l -s`.
- `stdout.txt` / `stderr.log`: Raw CLI output and errors.
- `result.json`: Execution metadata (`status` ok, failed or timeout; `exit_code`, `duration_seconds`, `cwd_wsl`, `swarm`, `model`, `effort`, and with `--output-format json` `conversation_id`, `agy_status`, `usage`).
- `response.md` and `last_message.md`: the response text (the `response` field when the output is JSON).

## Use from agent-delivery
Slots with provider `agy-wsl` (for example `agy-wsl:gemini-4-hydrogen-high:high`) run this runner. Install it beside `agent-delivery`. Tests: `python -m unittest discover -s tests`.

---
name: agy-wsl-headless
description: Execute Google Antigravity (`agy -p`) inside WSL (Ubuntu) non-interactively from Windows or WSL, with built-in support for native `swarm` orchestration (`swarm`, `post_message`, `read_board`, `swarm_wait`), Windows-to-WSL path translation, quote-safe `bash -l -s` stdin dispatch, `--print-timeout`, `--dangerously-skip-permissions`, and telemetry (`result.json`).
compatibility: Requires WSL with Ubuntu and Antigravity CLI (`agy` 1.5.14+, e.g. `/home/dhaka/.local/bin/agy`) signed in.
tags: [antigravity, agy, wsl, headless, swarm, multi-agent, cli, automation]
---

# Antigravity WSL Headless & Swarm Runner (`agy-wsl-headless`)

Executes Google Antigravity (`agy -p`) inside WSL (Ubuntu) from Windows PowerShell or directly inside WSL, including multi-agent **native `swarm` orchestration**.

## Why a Dedicated WSL Runner?
1. **Quote-safe Windows → WSL dispatch**: Passing complex multi-line or swarm prompts through `wsl -e bash -lc '...'` from Windows PowerShell truncates or mangles nested quotes. `agy_wsl_headless.py` streams a generated script over `wsl -e bash -l -s` stdin and reads the prompt from a translated file, preserving every quote and newline.
2. **Automatic path translation**: Windows paths (`E:\Projects\...`) passed to `-C`, `--prompt-file`, `--add-dir`, or `--json-schema` are automatically translated to `/mnt/e/Projects/...`.
3. **Swarm-ready defaults**: In `agy` 1.5.14+, native swarm tools (`swarm`, `post_message`, `read_board`, `swarm_wait`) and builtin skills (`native_swarm`, `swarm_monitor`, `swarm_pane`, `swarm_narrator`) are built directly into `-p` headless sessions. Note that the read-only Swarm Aux Pane UI (`~/.gemini/antigravity-cli/builtin/plugins/swarm`) is skipped in headless mode while the full swarm runtime and board state run normally.

## Practical Rules for Headless & Swarm Runs
- Always pass `--auto-approve` (`--dangerously-skip-permissions`) or `--swarm` so the coordinator and workers do not stall on interactive approval prompts.
- Set `--print-timeout` high enough for multi-turn worker coordination (e.g. `120s`, `600s`, or `0s` to wait until the turn finishes).
- On-disk swarm artifacts (`board.jsonl`, `members.json`, `swarm.json`) are written under `~/.gemini/antigravity-cli/brain/<conversation_id>/.system_generated/swarm/` inside WSL.

## Quickstart Recipes

### 1. Basic WSL Smoke Test
```bash
python "scripts/agy_wsl_headless.py" \
  --print-timeout 60s \
  "Reply with exactly: WSL_AGY_OK"
```

### 2. Headless Swarm Orchestration (`--swarm`)
`--swarm` automatically enables `--auto-approve` (`--dangerously-skip-permissions`) and sets a default `--print-timeout 300s` (override with `--print-timeout`).
```bash
python "scripts/agy_wsl_headless.py" \
  --swarm \
  --print-timeout 180s \
  -C "E:\Projects\trishul-tactical-engine" \
  --prompt-file "briefs/swarm-task.md"
```

### 3. Dry-Run Verification (0 Quota Spent)
```bash
python "scripts/agy_wsl_headless.py" \
  --swarm \
  -C "E:\Projects\trishul-tactical-engine" \
  --dry-run \
  "Test swarm dry run"
```

## Telemetry and Artifacts
Every run records artifacts under `%TEMP%/agy-wsl-headless-runs/<stamp>-<id>/` (or `--out-dir`):
- `prompt.md`: Exact prompt submitted.
- `dispatch.sh`: Exact bash script streamed to `wsl -e bash -l -s`.
- `stdout.txt` / `stderr.log`: Raw CLI output and errors.
- `result.json`: Execution metadata (`status`, `exit_code`, `duration_seconds`, `cwd_wsl`, `swarm`).

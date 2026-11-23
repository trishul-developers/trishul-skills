---
name: agy-quota
description: Inspect and monitor real-time Antigravity rate limit quotas, credit pools (prompt/flow credits), account plan tier, and per-model availability via the local language server (127.0.0.1). Supports querying all models or filtering by specific model ID/substring (e.g. gemini-3.8-flash, claude-sonnet-4-6, claude-opus-4-6-thinking, gpt-oss-120b-medium).
compatibility: Requires local Antigravity Language Server (agy or Antigravity IDE/App running).
tags: [antigravity, agy, quota, rate-limit, credits, models, diagnostics]
---

# Antigravity Local Language Server Quota & Plan Monitor

This skill provides an automated interface to query the local Antigravity Language Server running on `127.0.0.1`. It inspects your account's real-time credit pools, plan tiers, and per-model rate limit quota status.

## Core Capabilities

- **Account & Plan Visibility**: Query subscription tier (e.g., `Pro`, `TEAMS_TIER_PRO`), monthly credit allocations, and currently available prompt and flow credit balances.
- **Model Rate Limit Quotas**: Check the exact `remainingFraction` (e.g., `99.1%`) and upcoming `resetTime` per model.
- **Specific Model Filtering**: Target any specific model ID or fuzzy label (e.g., `gemini-3.8-flash-high`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`, `gpt-oss-120b-medium`, or substrings like `flash`, `claude`, `opus`).
- **Flexible Output Formats**:
  - `table`: Human-readable formatted terminal table with account and quota summaries.
  - `json`: Machine-readable structured JSON for automated pipelines, scripts, and subagents.
  - `quiet`: Raw remaining percentage or balances for shell scripting.
  - `raw`: Full unparsed protobuf JSON response from `GetUserStatus`.
- **Zero Third-Party Dependencies**: Pure Python 3 standard library script (`urllib`, `json`, `argparse`).

---

## Connection & Environment Prerequisites

The script connects to the local Antigravity language server HTTP Connect/gRPC bridge. In active Antigravity CLI, IDE, or agent subshells, the necessary connection variables are pre-populated:

- `ANTIGRAVITY_LS_ADDRESS`: Host and port of the local language server (e.g. `localhost:46627`).
- `ANTIGRAVITY_CSRF_TOKEN`: Session CSRF authorization token (passed via `x-codeium-csrf-token`).

When running **outside** an active Antigravity session (for example, from standalone WSL, Codex, or cron):
- Either export `ANTIGRAVITY_LS_ADDRESS` and `ANTIGRAVITY_CSRF_TOKEN` (or pass `--addr` and `--csrf`, which set both environment variables),
- Or pass `--via-agy` to run `check_quota.py` inside a short `agy -p` session where both variables are automatically populated.

*(Note: When invoking commands that communicate over loopback network sockets, ensure commands run unsandboxed / with `BypassSandbox: true` if container network isolation is active.)*

---

## Quickstart Recipes

The bundled script is located at:
`~/.gemini/config/skills/agy-quota/scripts/check_quota.py`

### 1. View Full Account Plan & All Model Quotas

```bash
python3 ~/.gemini/config/skills/agy-quota/scripts/check_quota.py
```

Output:
```text
============================================================
ANTIGRAVITY ACCOUNT & PLAN STATUS
============================================================
Plan:                 Pro (TEAMS_TIER_PRO)
Prompt Credits:       500 / 50,000 (monthly)
Flow Credits:         100 / 150,000 (monthly)

---------------------------------------------------------------------------
MODEL                        MODEL ID                 REMAINING   RESET TIME
---------------------------------------------------------------------------
Gemini 3.8 Flash (High)      gemini-3.8-flash-high     99.0%      2026-11-23T06:27:26Z
Gemini 3.8 Flash (Medium)    gemini-3.8-flash-medium   99.0%      2026-11-23T06:27:26Z
Gemini 3.8 Flash (Low)       gemini-3.8-flash-low      99.0%      2026-11-23T06:27:26Z
Claude Sonnet 4.6 (Thinking) claude-sonnet-4-6        100.0%      2026-11-23T06:38:09Z
Claude Opus 4.6 (Thinking)   claude-opus-4-6-thinking 100.0%      2026-11-23T06:38:09Z
GPT-OSS 120B (Medium)        gpt-oss-120b-medium      100.0%      2026-11-23T06:38:09Z
---------------------------------------------------------------------------
```

---

### 2. Check Quota for a Specific Model

Filter by exact model ID or case-insensitive substring:

```bash
# Check Gemini 3.8 Flash High
python3 ~/.gemini/config/skills/agy-quota/scripts/check_quota.py -m gemini-3.8-flash-high

# Check Claude models
python3 ~/.gemini/config/skills/agy-quota/scripts/check_quota.py -m claude

# Check GPT-OSS
python3 ~/.gemini/config/skills/agy-quota/scripts/check_quota.py -m gpt-oss-120b-medium
```

---

### 3. Structured JSON Output (For Automation & Agents)

```bash
# Get JSON object for a specific model
python3 ~/.gemini/config/skills/agy-quota/scripts/check_quota.py -m claude-sonnet-4-6 -f json

# Get complete JSON payload including plan status and all models
python3 ~/.gemini/config/skills/agy-quota/scripts/check_quota.py -f json
```

Example JSON output for a model:
```json
{
  "label": "Claude Sonnet 4.6 (Thinking)",
  "modelId": "claude-sonnet-4-6",
  "remainingFraction": 1.0,
  "resetTime": "2026-11-23T06:38:09Z",
  "supportsImages": true,
  "allowedTiers": [
    "TEAMS_TIER_PRO",
    "TEAMS_TIER_TEAMS"
  ],
  "hasQuotaLimit": true
}
```

---

### 4. Quiet Mode for Shell Scripts

Extract just the remaining percentage for conditional checks:

```bash
REMAINING=$(python3 ~/.gemini/config/skills/agy-quota/scripts/check_quota.py -m gemini-3.8-flash-high -f quiet)
echo "Gemini Flash Remaining: $REMAINING"
```

---

### 5. Check Credit Balances Only

```bash
python3 ~/.gemini/config/skills/agy-quota/scripts/check_quota.py --credits-only
```

---

## Direct RPC Specification

If calling via `curl` directly without Python:

```bash
curl -sS -X POST \
  "http://${ANTIGRAVITY_LS_ADDRESS:-localhost:5387}/exa.language_server_pb.LanguageServerService/GetUserStatus" \
  -H "Content-Type: application/json" \
  -H "x-codeium-csrf-token: ${ANTIGRAVITY_CSRF_TOKEN}" \
  -d '{}'
```

Key fields in response:
- `.userStatus.planStatus`: Credit pools (`availablePromptCredits`, `availableFlowCredits`, `monthlyPromptCredits`, `monthlyFlowCredits`).
- `.userStatus.cascadeModelConfigData.clientModelConfigs[]`: Model array with `.modelId`, `.label`, and `.quotaInfo.remainingFraction` / `.quotaInfo.resetTime`.

---

## CLI Reference Options

| Flag | Short | Description |
| :--- | :--- | :--- |
| `--model <ID>` | `-m` | Filter by specific model ID or label substring |
| `--format <type>`| `-f` | Output format: `table` (default), `json`, `quiet`, `raw` |
| `--credits-only` | | Show only prompt and flow credit balances |
| `--models-only` | | Show only model quota table without plan header |
| `--all` | | Include disabled models or models without active quota limits |
| `--addr <host:port>` | | Override language server address (default: `$ANTIGRAVITY_LS_ADDRESS`) |
| `--csrf <token>` | | Override CSRF token (default: `$ANTIGRAVITY_CSRF_TOKEN`) |

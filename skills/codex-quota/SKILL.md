---
name: codex-quota
description: Inspect and monitor real-time OpenAI Codex rate limits, rolling quota windows (5-hour and 7-day windows), account plan tiers (Plus, Pro, Team, Enterprise), reset countdowns, and model availability non-interactively without opening the interactive TUI, desktop app, or browser. Supports querying overall quota or targeting specific models (e.g. gpt-6.2-sol, gpt-6.1-terra, gpt-6.2-astra, gpt-6-luna).
compatibility: Requires codex CLI on PATH and signed in.
tags: [codex, openai, quota, rate-limit, limits, models, diagnostics]
---

# OpenAI Codex Non-Interactive Quota & Rate Limit Monitor

This skill inspects real-time OpenAI Codex rate limits, rolling quota consumption windows, and subscription plan details **completely headlessly** without launching the interactive terminal TUI, desktop app, or web browser.

## Core Capabilities

- **100% Non-Interactive / Headless**: Communicates directly with the Codex background JSON-RPC 2.0 app-server protocol (`codex app-server --stdio`).
- **Dual Rolling Window Tracking**:
  - **Primary Window**: 5-hour rolling rate limit (used percentage, remaining percentage, exact UTC reset timestamp, relative countdown).
  - **Secondary Window**: 7-day weekly rolling rate limit (used percentage, remaining percentage, exact UTC reset timestamp, relative countdown).
- **Subscription & Credits Status**:
  - Active subscription tier (`Plus`, `Pro`, `Team`, `Enterprise`).
  - Account email.
  - Credits balance and available rate limit reset credits.
- **Model Availability & Reasoning Tiers**:
  - Filter by specific model name or substring (`-m gpt-6.2-sol`, `-m sol`, `-m terra`, `-m astra`).
  - View supported reasoning efforts (`low`, `medium`, `high`, `xhigh`, `max`, `ultra`).
- **Flexible Formats**:
  - `table`: Human-readable formatted terminal display.
  - `json`: Structured JSON for automation, CI, and multi-agent coordination.
  - `quiet`: Raw remaining quota percentage for shell conditionals.
  - `raw`: Full unparsed JSON-RPC payload.

---

## Quickstart Recipes

The bundled script is located at:
`<skill-dir>/scripts/check_codex_quota.py`

### 1. View Account Plan, Windows & Active Models

```bash
python3 <skill-dir>/scripts/check_codex_quota.py
```

Example Output:
```text
=================================================================
OPENAI CODEX ACCOUNT & RATE LIMIT STATUS
=================================================================
Plan:                 PLUS
Account Email:        user@example.com
Credits Balance:      0
Reset Credits:        0 available

-----------------------------------------------------------------
ROLLING RATE LIMIT WINDOWS
-----------------------------------------------------------------
• Primary (300m / 5h)  : 100% used (0% remaining)
  Reset Timestamp     : 2026-11-23 05:31:49 UTC (in 3h 40m)
• Secondary (7d window) : 31% used (69% remaining)
  Reset Timestamp     : 2026-11-29 14:39:27 UTC (in 6d 12h)
-----------------------------------------------------------------

AVAILABLE MODELS (ACTIVE TIER):
  • GPT-6.2-Sol          (ID: gpt-6.2-sol)
  • GPT-6.2-Astra        (ID: gpt-6.2-astra)
  • GPT-6.1 Terra        (ID: gpt-6.1-terra)
  • GPT-6-Sol            (ID: gpt-6-sol)
  • GPT-6-Luna           (ID: gpt-6-luna)
  • GPT-5.6-Sol          (ID: gpt-5.6-sol)
  • GPT-5.6-Terra        (ID: gpt-5.6-terra)
  • GPT-5.6-Luna         (ID: gpt-5.6-luna)
-----------------------------------------------------------------
```

---

### 2. Check Specific Model

```bash
# Filter by exact ID or substring
python3 <skill-dir>/scripts/check_codex_quota.py -m gpt-6.2-sol

# Check all 'terra' models
python3 <skill-dir>/scripts/check_codex_quota.py -m terra
```

---

### 3. Machine-Readable JSON for Scripts & Agents

```bash
python3 <skill-dir>/scripts/check_codex_quota.py -m gpt-6.2-sol -f json
```

Output:
```json
{
  "account": {
    "type": "chatgpt",
    "email": "user@example.com",
    "planType": "plus"
  },
  "planType": "plus",
  "primaryWindow": {
    "used": "100%",
    "remaining": "0%",
    "remainingVal": 0,
    "reset": "2026-11-23 05:31:49 UTC",
    "countdown": "in 3h 40m",
    "windowDurationMins": 300
  },
  "secondaryWindow": {
    "used": "31%",
    "remaining": "69%",
    "remainingVal": 69,
    "reset": "2026-11-29 14:39:27 UTC",
    "countdown": "in 6d 12h",
    "windowDurationMins": 10080
  },
  "credits": {
    "balance": "0",
    "unlimited": false
  },
  "rateLimitResetCredits": {
    "availableCount": 0
  },
  "targetModel": "gpt-6.2-sol",
  "matchedModels": []
}
```

---

### 4. Fast Shell Conditionals (Quiet Mode)

```bash
REMAINING=$(python3 <skill-dir>/scripts/check_codex_quota.py -f quiet)
echo "Primary Quota Remaining: $REMAINING"
if [ "$REMAINING" = "0%" ]; then
    echo "Warning: Codex primary quota is exhausted."
fi
```

---

## Technical Protocol Details

Codex communicates via the JSON-RPC 2.0 app-server protocol:
1. Spawns `codex app-server --stdio` in background.
2. Handshakes via `initialize` (`clientInfo: {name, version}`) followed by `initialized` notification.
3. Requests:
   - `account/read`: Account email, plan type, user ID.
   - `account/rateLimits/read`: Primary & secondary windows, usage percentage, timestamps, reset credits.
   - `model/list`: Complete model catalog with reasoning tier metadata.

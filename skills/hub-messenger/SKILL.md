---
name: hub-messenger
description: Zero-model messenger daemon and self-wake waiter for Trishul Agent Hub. Periodically polls participant inboxes and wakes idle workers with unread mail via detached CLI resumption, in-session self-wait (hub_wait), or logging, eliminating expensive model-turn polling chats.
compatibility: Windows (PowerShell, Git Bash) and POSIX. Python 3 standard library only.
tags: [hub, messenger, daemon, standby, wake, idle, tte]
---

# Hub Messenger

`hub-messenger` is a zero-model standby and wake daemon for the Trishul Agent Hub (`http://127.0.0.1:8765`).

## Purpose & Background

In a multi-agent orchestration setup, agents enter idle standby after finishing their turns. To notify agents when new mail arrives, LLM-based polling chats (`messenger-claude`, `messenger-codex`) consume model quota merely to call `inbox_wait` and check participant states.

`hub-messenger` runs as a lightweight, zero-model Python daemon that polls the Trishul Agent Hub REST API directly (`GET /participants?project=tte`), identifies idle participants with unread deliveries, and triggers targeted turn resumption.

---

## Wake Rules (Role `messenger` v3)

A participant is woken if and only if **all** of the following conditions are met:
1. **Pending Mail**: `pending > 0`.
2. **Not Waiting**: `waiting == False` (the participant is not currently blocked in an active `inbox_wait` MCP tool call).
3. **Trigger Criteria**:
   - The pending delivery count has **risen** since the last wake (`pending > last_pending`), OR
   - At least **30 minutes** (1,800 seconds) have elapsed since its last wake.
4. **Manager Exclusion**: The project manager (`manager` / `project-manager`) is **NEVER** woken under any circumstances. Only the human owner wakes the manager.
5. **Wake Message**: The resumption text is exactly: `"Check your hub inbox."`

---

## Target Modes & Configuration

Wake behavior is configured in `~/.hub-messenger/config.json` (outside of all repositories; `%LOCALAPPDATA%\hub-messenger\config.json` is supported as a fallback). Every participant defaults to `log` mode unless explicitly configured.

```json
{
  "targets": {
    "orchestrator-codex": {
      "mode": "codex",
      "thread_id": "<codex-session-uuid>",
      "timeout": 60
    },
    "orchestrator-claude": {
      "mode": "claude",
      "session_id": "<claude-session-id>",
      "timeout": 900
    },
    "custom-worker": {
      "mode": "command",
      "command": ["python", "C:/path/to/worker_wake.py"],
      "timeout": 60
    }
  }
}
```

### Supported Modes:
- **`log`** (default for every target): Logs and prints `[LOG] Would wake participant '<name>': 'Check your hub inbox.'` without spawning external processes.
- **`codex`**: Executes `codex queue --thread <thread-id> --resume --message "Check your hub inbox."` detached and non-blocking. This queues a new turn after the chat's current turn ends instead of starting a second turn in parallel. Note: the Codex app-server daemon must be running; otherwise the prompt is only stored. Because `codex queue` returns quickly once queued, its timeout does not bound a turn (default timeout: 60 s).
- **`claude`**: Executes `claude -p --resume <session-id> "Check your hub inbox."` detached and non-blocking (900 s timeout). **Notice:** Strictly for headless/non-interactive CLI runs only; **not** for a chat session currently open in the Claude desktop app (see [Waking Claude chats (`hub_wait`)](#waking-claude-chats-hub_wait) below).
- **`command`**: Executes an explicit argument list specified in the target configuration (default timeout: 60 s).

### Concurrency & Lifecycle Safeguards:
- Never launches more than one wake process for the same target simultaneously. If a previous wake process is still active, subsequent wake triggers for that target are skipped until the active process terminates.
- **Wake Timeouts**: Defaults to 900 seconds (15 minutes) only for `claude` mode (where Claude Code runs the turn synchronously to completion), and 60 seconds for `codex` mode (where `codex queue` enqueues and exits quickly) and `command` mode. If a wake process exceeds its timeout, `hub-messenger` terminates it (`proc.terminate()`), terminating a turn in progress or hung command to prevent stalled runs.
- **Single-Instance OS File Lock**: An OS-level advisory file lock (`msvcrt.locking(fd, LK_NBLCK, 1)` on Windows, `fcntl.flock(fd, LOCK_EX|LOCK_NB)` on POSIX) on `state.pid` held on an open file handle ensures that exactly one daemon instance runs at a time. The OS drops the lock automatically when the process terminates. Diagnostic details (PID, start time) are written to the file for human inspection but are never used to decide lock ownership; leftover diagnostics files from killed instances do not block new instances.
- Subprocesses are spawned detached and non-blocking with `stdin=DEVNULL`, and exit codes are logged.

---

## Token Handling & Security

The daemon accepts a bearer token via `--token-file <path>`:
- The token is read at runtime into memory **only**.
- It is **never** logged, printed, echoed, passed as a command-line argument, or written to disk.
- Log and error messages refer strictly to the file path (e.g. `'C:\Users\...\owner.token'`), never its contents.

Available token options under `C:\Users\tosum\TrishulAgentHub\tokens`:
- `runtime.token`: Recommended daemon runtime token (least privilege; listing participants is allowed for any authenticated actor per `permissions.py:426`).
- `coordinator.token`: Participant token for coordinator.
- `controller.token`: Controller credential.
- `app-codex.token`: Codex app client credential.
- `app-claude-code.token`: Claude Code app client credential.
- `app-antigravity.token`: Antigravity app client credential.
- `owner.token`: Trishul Agent Hub owner token (administrative operations).

---

## CLI Usage

### Basic Polling Run
```bash
python skills/hub-messenger/scripts/hub_messenger.py --token-file "C:\Users\tosum\TrishulAgentHub\tokens\runtime.token"
```

### Single Cycle Verification (--once & --dry-run)
```bash
python skills/hub-messenger/scripts/hub_messenger.py --token-file "C:\Users\tosum\TrishulAgentHub\tokens\runtime.token" --once --dry-run
```

### Command Options:
- `--hub-url <url>`: Agent Hub base URL (default: `http://127.0.0.1:8765`).
- `--project <name>`: Project name to poll (default: `tte`, automatically resolves to `trishul-tactical-engine` if aliased).
- `--token-file <path>`: Path to file containing bearer token (recommend a least-privilege token like `runtime.token`).
- `--interval <seconds>`: Poll interval in seconds (default: `60`).
- `--config <path>`: Path to target configuration JSON (default: `~/.hub-messenger/config.json`, fallback: `%LOCALAPPDATA%\hub-messenger\config.json`).
- `--state-file <path>`: Path to participant wake state persistence file (default: `~/.hub-messenger/state.json`).
- `--log-file <path>`: Path to rotating log file (default: `~/.hub-messenger/hub-messenger.log`).
- `--once`: Execute a single poll cycle and exit immediately.
- `--dry-run`: Force all targets into `log` mode.

---

## Service Operation & Automation

### Running at Logon via Windows Task Scheduler
On Windows, when running under Microsoft Store Python, the package execution path can fail under Task Scheduler with `0x8007010B`. The execution path `%LOCALAPPDATA%\Microsoft\WindowsApps\pythonw.exe` avoids this issue. Additionally, writes under `%LOCALAPPDATA%` are redirected to the store package local cache, so the daemon runs with defaults anchored at `~/.hub-messenger/` (`C:\Users\tosum\.hub-messenger\`).

To register `TrishulHubMessenger` as a background task running at logon with no console window:

```powershell
$action = New-ScheduledTaskAction -Execute "$env:LOCALAPPDATA\Microsoft\WindowsApps\pythonw.exe" -Argument "E:\Projects\Skills\skills\hub-messenger\scripts\hub_messenger.py --token-file C:\Users\tosum\TrishulAgentHub\tokens\runtime.token"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "TrishulHubMessenger" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Trishul Agent Hub Standby Messenger Daemon"
```

### Stopping the Daemon
If running via Task Scheduler:
```powershell
Stop-ScheduledTask -TaskName "TrishulHubMessenger"
```

If running in a shell or console:
Press `Ctrl+C`, or terminate the background process:
```powershell
Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%hub_messenger.py%'" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

### Log File Location & Rotation
Logs are written to:
`~/.hub-messenger/hub-messenger.log`

The log handler automatically rotates when the file reaches 1 MB, preserving up to 3 historical backups (`hub-messenger.log.1`, `hub-messenger.log.2`, `hub-messenger.log.3`).

---

## Waking Claude Chats (`hub_wait`)

### Why the Daemon Does Not Wake Claude Desktop Chats
`hub_messenger.py` wakes Codex chats safely via `codex queue`. However, it **cannot** safely wake a Claude desktop chat via the CLI:
1. `claude -p --resume <session-id>` on a session concurrently open in the Claude desktop app causes two independent writers to interleave into a single transcript file, resulting in state corruption.
2. `claude --bg --resume <session-id>` forks a separate detached copy rather than resuming the existing UI session.

The authoritative, safe route for Claude desktop chats is **in-session self-wake** via `hub_wait.py`. The Claude chat launches `hub_wait` as a background command before ending its turn; when the command exits, the Claude desktop app automatically wakes the same chat in-session (verified 2026-11-09). Waiting in Python costs zero model tokens.

### The Self-Wake Loop
Before ending each turn, a Claude worker runs the following loop:
1. **Background Waiter**: The chat runs `hub_wait.py` via the bash tool with `run_in_background: true`.
2. **App Wake**: When incoming mail arrives (`pending > 0`) or `--max-wait` expires, `hub_wait.py` prints one informative line and exits `0`.
3. **Turn Resumption**: The Claude desktop app wakes the chat with the exit output.
4. **Process Mail & Re-Arm**: The chat reads its hub inbox (`mcp__hub__inbox_receive` or CLI), performs its task, sends its replies, acknowledges deliveries, and immediately starts `hub_wait` in the background again.

### Command for Claude Chats to Run
```bash
python "C:\Users\tosum\.claude\skills\hub-messenger\scripts\hub_wait.py" --participant <name> --token-file "C:\Users\tosum\TrishulAgentHub\tokens\runtime.token"
```

Deployed path in the global Claude skills directory:
`C:\Users\tosum\.claude\skills\hub-messenger\scripts\hub_wait.py`

### Waiter Options:
- `--participant <name>`: Required. Participant name to watch.
- `--token-file <path>`: Required. Token file path (read in-memory only; never logged or saved).
- `--project <name>`: Project name (default: `trishul-tactical-engine`).
- `--hub-url <url>`: Hub URL (default: `http://127.0.0.1:8765`).
- `--interval <seconds>`: Poll interval in seconds (default: `30`, minimum: `5`).
- `--max-wait <seconds>`: Maximum wait duration before exiting with re-arm (default: `0` = no limit). Setting e.g. `--max-wait 1800` wakes the chat every 30 minutes to re-arm rather than remaining silent indefinitely.
- `--lock-dir <path>`: Directory for OS lock files (default: `~/.hub-messenger`).

### Concurrency & Exit Codes:
- **Lock Guard**: An OS lock (`hub_wait.<participant>.lock`) ensures exactly one waiter runs per participant. If a duplicate waiter is launched for the same participant, it prints `hub_wait: already waiting for <participant> (pid <n>)` and exits `4` immediately. The background task completing wakes the chat once, which is harmless.
- **Exit Codes**:
  - `0`: Mail arrived (`hub_wait: <participant> has <n> pending message(s)...`) OR max wait reached (`hub_wait: no mail after <s> s. Start hub_wait again.`).
  - `3`: Participant not found in the hub listing.
  - `4`: Another waiter is already active for this participant.

### Known Limitations:
1. **App Closure**: The waiter process terminates if the Claude desktop app or chat is closed and is not restored on resumption; a reopened chat must start `hub_wait` again.
2. **Turn Cost**: Each self-wake costs one model turn in the Claude desktop app.
3. **Mid-Turn Messages**: A chat that is busy computing mid-turn is woken only after its current turn ends.
4. **Daemon Target Mode**: In `~/.hub-messenger/config.json`, the daemon must keep any Claude desktop participant in `log` mode so that the daemon never attempts a secondary CLI wake.

### Optional Future Enhancement: Stop Hook (`asyncRewake`)
A Claude Code Stop hook (e.g. `asyncRewake`) could run `hub_wait` automatically when any turn finishes without manual tool invocation. This hook pattern is currently unverified in the Claude desktop app harness and is documented for future exploration only; do not install or configure it without testing.

---

## Known Risks

> [!WARNING]
> **1. Desktop App Session Conflict Risk**
> A desktop chat session resumed from the CLI (`codex exec resume` or `claude -p --resume`) may conflict with the same chat session simultaneously open in the Claude desktop app or Codex desktop application (resulting in two concurrent writers to a single session transcript, or wake responses that the desktop app UI fails to reflect).
> **Mitigation:** Claude desktop chats use in-session `hub_wait.py`. Codex chats use `codex queue` (which enqueues turns safely via the app server). Targets default to `log` mode in the daemon.

> [!WARNING]
> **2. Busy Mid-Turn Participant Risk**
> A participant that is busy executing a long tool or thinking mid-turn is also reported by the hub as `waiting == False` (since it is not currently blocking in `inbox_wait`). Triggering a CLI wake while a participant is actively computing could prompt the provider runtime to launch an unexpected second turn or report an execution conflict.
> **Mitigation:** The 30-minute re-wake rule strictly limits daemon re-triggering, while `hub_wait` runs entirely in-session and wakes the chat only after turn completion.

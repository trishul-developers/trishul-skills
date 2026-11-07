---
name: thub-messenger
description: Send, receive, and orchestrate messages between agent sessions (Claude Code, Codex, Antigravity, and headless participants) via the Trishul Agent Hub (`thub`). Use this whenever coordinating tasks between sessions, waiting on external agent deliverables with `inbox_wait`, dispatching headless participants, inspecting dead letters, or checking project mailboxes.
compatibility: Requires Trishul Agent Hub running on loopback (127.0.0.1:8765 or AGENT_HUB_PORT) and an active session credential or token.
tags: [agent-hub, messenger, multi-agent, mcp, orchestration, trishul]
---

# Trishul Agent Hub Messenger (`thub-messenger`)

This skill connects AI agent sessions to the local **Trishul Agent Hub** (`thub`), providing dependable, asynchronous inter-agent communication, headless participant execution, and mailbox supervision across Claude, Codex, and Antigravity.

## Architecture Principles
1. **Sessions Own the Workflow**: The hub provides deterministic delivery, idempotency, and session binding. Role prompts and controlling agents define the collaboration graph.
2. **First-Class Participants**:
   - **Interactive Sessions**: Open Claude, Codex, or Antigravity IDE sessions joined via MCP that long-poll with `inbox_wait`.
   - **Headless Participants**: Automated CLI workers started on demand by the hub runner when mail arrives.
3. **Idempotency & Versioning**: All mutating requests require an `idempotency_key` (UUIDv7 or task-scoped hash). State updates use optimistic concurrency.

## Tools and Operations

### 1. Waiting for Mail (`inbox_wait`)
When waiting for an external agent (Codex, Claude, or Antigravity) to complete a handoff, use `inbox_wait`:
- Never poll in a busy CPU loop.
- Pass `timeout_seconds` (e.g. 300 to 1800).
- Only wait when delegating outside the current session.

```json
{
  "tool": "inbox_wait",
  "arguments": {
    "timeout_seconds": 600,
    "project": "trishul-tactical-engine"
  }
}
```

### 2. Sending a Message (`message_send`)
Send a task brief or review feedback to a designated recipient:

```json
{
  "tool": "message_send",
  "arguments": {
    "recipient": "trishul-tactical-engine/orchestrator-codex",
    "subject": "Brief: Spec Step G02.08 Movement Pathfinding",
    "body": "Implement pathfinding waypoint cache per spec G02.08. Tests must pass before handoff.",
    "idempotency_key": "step-g02-08-brief-v1",
    "thread_id": "thread-g02-batch-2"
  }
}
```

### 3. Dispatching a Headless Participant (`participant_run`)
To start an unattended headless agent for batch or mechanical work:
- Role: Defined in the hub catalog (e.g. `executor-antigravity`, `implementor-codex`).
- Runner executes `codex exec`, `claude -p`, or `agy -p`.

```bash
thub runner dispatch --participant "executor-antigravity" --project "trishul-tactical-engine" --task-file "briefs/task.md"
```

### 4. Health & Dead Letter Inspection (`thub doctor`)
```bash
thub doctor
thub deliveries list --status failed
thub session list --active
```

## Best Practices
- **No Stored Handles**: Never persist temporary session handles in files or git; request a fresh handle or reconnect on restart.
- **Loopback Only**: Connect strictly to `127.0.0.1`, never `localhost`, to avoid DNS resolution latency on Windows.
- **Failures are Explicit**: If a participant cannot be reached or times out, the hub emits a dead-letter event. Always handle timeouts gracefully.

---
name: chatgpt-role-bridge
description: >-
  Temporary project-local bridge enabling ORCHESTRATOR-LOCAL to communicate with persistent
  cloud ChatGPT roles (such as DESIGN_OWNER and REVIEWER) via the proven PoC-001 Session Host.
  Use when coordinating Phase 2 architecture freeze, Gate 1 design approval, or exact-SHA code
  reviews with cloud roles without manual copy-pasting.
---

# ChatGPT Role Bridge (PoC-001 Wrapper)

The `chatgpt-role-bridge` skill connects Antigravity `ORCHESTRATOR-LOCAL` to persistent, provider-neutral cloud role sessions hosted on ordinary ChatGPT.

> [!IMPORTANT]
> **Sessions are disposable; workflow state is durable.**
> ChatGPT transcript content is NOT durable workflow state.
> The bridge is a transport utility only. Important outcomes (`DESIGN_SCHEMA_FREEZE_APPROVED`, `PRE_GATE_APPROVED`, `CHANGES_REQUIRED`, `SOURCE_REVIEW_PASS`) must always be posted durably to GitHub Issue #3 / PR #4 by `ORCHESTRATOR-LOCAL`.

---

## Logical Role Slots

Slot Name | Logical Role | Authority & Responsibilities | Bootstrap Template
:--- | :--- | :--- | :---
`phase2-design-owner` | `DESIGN_OWNER` | Final architecture, schema freeze, canonical contracts, ADRs, Amendment A-01 | [phase2-design-owner-bootstrap.txt](./resources/phase2-design-owner-bootstrap.txt)
`phase2-reviewer` | `REVIEWER` | Independent read-only review of exact candidate commit SHAs; verify invariants | [phase2-reviewer-bootstrap.txt](./resources/phase2-reviewer-bootstrap.txt)

---

## Operating Invariants

1. **Ordinary Chat Only**: Fails closed immediately if the session opens in Work or if surface is unverified (`FORBIDDEN_SURFACE` / `SURFACE_UNVERIFIED`).
2. **Attach to Existing Browser Only**: Connects to the user's already-running, explicitly configured loopback CDP browser. Never launch a browser, create a second browser instance, or fall back to a separate profile. If the CDP endpoint or profile authority cannot be verified, stop without opening ChatGPT or changing browser state.
3. **Envelope Enforcement**: Outgoing tasks use `CLOUD_ROLE_REQUEST v1`. Incoming results must start with `CLOUD_ROLE_RESULT v1`. Mismatches in `request_id`, `role`, or `candidate_sha` fail closed.
4. **Generation & CAS Lifecycle**: Reuses PoC-001 generation compare-and-swap. Stale generations reject immediately.
5. **No Secret Storage**: Only non-secret locators, profile IDs, generations, and timestamps are stored. Browser profiles and credentials remain local and gitignored under `.session-host/`.
6. **No Spontaneous Session Creation**: Do NOT create cloud ChatGPT conversations during routine skill inspection. Only create/bind sessions when explicitly instructed to bootstrap.

## Execution Permissions

For every bridge CLI invocation, browser/CDP operation, validation script that spawns processes, or other operational command in this skill, use the execution tool with escalated permissions (`sandbox_permissions: "require_escalated"`) and a short, specific justification. Do not first attempt the operation without escalation. If automatic approval rejects an escalation, stop that operation and report the rejection; do not retry through a different route or perform repeated approval attempts. Escalation grants execution access only and does not broaden the user's requested scope or authorize an external mutation that was not requested.

## Required Capabilities and Validation Status

The following requirements define supported behavior. The validation record at the end of this file reports which paths have been exercised and any limits on those checks.

| Capability | Requirement | Safe validation |
| :--- | :--- | :--- |
| Existing CDP browser | Attach only to an already-running browser over the configured loopback CDP endpoint. Preserve the browser process and its existing context; do not invoke Playwright browser launch. A missing endpoint, missing context, profile mismatch, or non-loopback endpoint fails closed. | With a test browser already running, verify the bridge attaches to that process and disconnects without terminating it. Verify absent/invalid endpoints do not launch a browser. |
| Project chat creation | Create an ordinary Chat directly in the explicitly selected ChatGPT Project. Verify project identity before sending the bootstrap and verify the resulting conversation remains attributable to that same Project. Never silently fall back to top-level Chat or Work. | Create a disposable test chat in the designated Project; verify ordinary Chat surface, project identity, and canonical conversation locator. |
| Chat rename | Rename only the explicitly identified conversation and verify the resulting title. Do not infer the target from whichever tab happens to be open. | Rename the disposable test chat to a unique temporary title and verify it in ChatGPT. |
| Chat deletion | Delete only an explicitly identified disposable test chat. Require a successful target identity check before the irreversible action; never delete a pre-existing role chat as a test. | Delete the disposable test chat created by the same validation run and verify it is no longer available. If target identity is ambiguous, stop. |
| Wait for response | Wait against the exact request ID in the exact conversation and active session generation. Return only after generation is complete and the result envelope validates against request ID, role, and exact candidate SHA; timeout or superseding user turn fails closed. | Send a unique test request to the disposable chat, wait for its response, and verify correlation and validation. Include timeout and wrong-request/SHA negative cases. |
| Suppress visible thinking | Ask the role chat for a concise final response in the required envelope, without progress narration or exposed reasoning. This is a response-format requirement; do not claim control over hidden model reasoning or depend on an unsupported ChatGPT UI setting. | Confirm the visible result is concise and envelope-only enough for parsing, while preserving required findings and typed status. |

Any validation that creates, renames, or deletes a ChatGPT conversation must use a disposable test conversation in the explicitly designated Project. Keep the locator and test title clearly marked as temporary, and clean up only that test conversation. Existing role chats and user conversations are never test fixtures.

---

## CLI Operations

The bridge CLI script is located at:
[scripts/bridge.mjs](./scripts/bridge.mjs)

Run commands using Node:
```powershell
node .agents/skills/chatgpt-role-bridge/scripts/bridge.mjs <command> [options]
```

### 1. `status`
Inspect current role slots, active generation numbers, session IDs, and locators.
```powershell
node .agents/skills/chatgpt-role-bridge/scripts/bridge.mjs status [--role-slot phase2-design-owner]
```

### 2. `ensure-role`
Verify that a logical role has an ACTIVE ChatGPT session. If missing, report status (or bootstrap if authorized).
```powershell
# Check status without creating
node .agents/skills/chatgpt-role-bridge/scripts/bridge.mjs ensure-role --role-slot phase2-design-owner --project https://chatgpt.com/g/g-p-<project-id>-<slug>/project

# Bootstrap only when explicitly authorized, using the already-running CDP browser
node .agents/skills/chatgpt-role-bridge/scripts/bridge.mjs ensure-role `
  --role-slot phase2-design-owner `
  --project https://chatgpt.com/g/g-p-<project-id>-<slug>/project `
  --bootstrap-if-missing `
  --cdp-endpoint http://127.0.0.1:9222 `
  --profile poc001a-win-chrome
```

Bootstrap requires an explicit Project locator, an already-running loopback CDP endpoint, and (when configured) the expected browser profile. It creates an ordinary Chat in that Project. It never launches a browser or falls back to a top-level Chat or Work.

To create a disposable Project chat outside a role slot, use `create-chat` with a unique `bridge-validation-` session ID and an explicit bootstrap prompt. Rename and delete are guarded by the saved Project locator and exact conversation title. Deletion is restricted to `bridge-validation-` sessions and refuses active role sessions.

```powershell
node .agents/skills/chatgpt-role-bridge/scripts/bridge.mjs create-chat `
  --session bridge-validation-<unique-id> `
  --project https://chatgpt.com/g/g-p-<project-id>-<slug>/project `
  --bootstrap "TEMPORARY BRIDGE VALIDATION ONLY. Reply briefly without progress narration." `
  --profile poc001a-win-chrome `
  --cdp-endpoint http://127.0.0.1:9222

node .agents/skills/chatgpt-role-bridge/scripts/bridge.mjs rename-chat `
  --session bridge-validation-<unique-id> `
  --locator <saved-conversation-locator> `
  --title "TEMP bridge-validation-<unique-id>" `
  --cdp-endpoint http://127.0.0.1:9222

node .agents/skills/chatgpt-role-bridge/scripts/bridge.mjs delete-chat `
  --session bridge-validation-<unique-id> `
  --locator <saved-conversation-locator> `
  --title "TEMP bridge-validation-<unique-id>" `
  --cdp-endpoint http://127.0.0.1:9222
```

### 3. `send-role`
Deliver an outgoing request wrapped in `CLOUD_ROLE_REQUEST v1` to the ACTIVE generation of a role.
```powershell
node .agents/skills/chatgpt-role-bridge/scripts/bridge.mjs send-role `
  --role-slot phase2-design-owner `
  --sha <exact-40-character-commit-sha> `
  --purpose DESIGN_SCHEMA_FREEZE `
  --prompt-file ./path/to/gate1-proposal.md `
  --cdp-endpoint http://127.0.0.1:9222
```

### 4. `wait-response`
Wait for and extract the NEW assistant response corresponding to the sent request. Validates `CLOUD_ROLE_RESULT v1` envelope and ensures the active generation has not changed.
```powershell
node .agents/skills/chatgpt-role-bridge/scripts/bridge.mjs wait-response `
  --role-slot phase2-design-owner `
  --request-id req-1728059000-abcd1234 `
  --sha <exact-40-character-commit-sha> `
  --timeout 180 `
  --cdp-endpoint http://127.0.0.1:9222
```

### 5. `replace-role`
Safely rotate/replace a role session using atomic compare-and-swap when a chat needs retirement.
```powershell
node .agents/skills/chatgpt-role-bridge/scripts/bridge.mjs replace-role `
  --role-slot phase2-design-owner `
  --expected-generation 1 `
  --profile poc001a-win-chrome `
  --cdp-endpoint http://127.0.0.1:9222
```

### 6. `parse-result`
Offline validation of a raw result payload against expected parameters.
```powershell
node .agents/skills/chatgpt-role-bridge/scripts/bridge.mjs parse-result `
  --text "CLOUD_ROLE_RESULT v1..." `
  --request-id req-123 `
  --role DESIGN_OWNER `
  --sha 01f448b174c69f2039581384534874152c2fafd3
```

---

## Envelope Specification

### Request Envelope (`CLOUD_ROLE_REQUEST v1`)
```text
CLOUD_ROLE_REQUEST v1

request_id: <unique-id>
role: <DESIGN_OWNER | REVIEWER>
repository: tosumitdhaka/agent-control-plane
issue: 3
pr: 4
candidate_sha: <exact commit SHA>
purpose: <DESIGN_SCHEMA_FREEZE | PRE_GATE_REVIEW | SOURCE_REVIEW>

<Task description, files to review, questions, or context>
```

### Result Envelope (`CLOUD_ROLE_RESULT v1`)
```text
CLOUD_ROLE_RESULT v1
request_id: <same request_id>
role: <DESIGN_OWNER | REVIEWER>
reviewed_sha: <exact commit SHA>
status: <TYPED_STATUS>

<Findings, decisions, or review notes>
```

#### Allowed Status Enums:
- **DESIGN_OWNER**:
  - `DESIGN_SCHEMA_FREEZE_APPROVED`
  - `PRE_GATE_APPROVED`
  - `CHANGES_REQUIRED`
  - `DECISION_PENDING`
- **REVIEWER**:
  - `SOURCE_REVIEW_PASS`
  - `PRE_GATE_APPROVED`
  - `CHANGES_REQUIRED`
  - `BLOCKED`

---

## Local Verification Runbook

Run deterministic local tests:
```powershell
node --test .agents/skills/chatgpt-role-bridge/tests/bridge.test.mjs
```

Verify that production tests remain completely unaffected:
```powershell
npm test
```

The CLI's `--cdp-endpoint` must be supplied for every browser operation; omission must never be treated as permission to launch a new browser. Use only an already-running browser's loopback CDP endpoint. All candidate SHAs must be complete 40-character commit SHAs.

### Latest workflow validation — 2026-10-06

Validation used the already-running Chrome instance at `http://127.0.0.1:9222` after its dedicated Session Host profile was verified. No browser was launched. The CDP listener remained active after the test connection closed.

- **Existing CDP attachment:** PASS. Validation attached through the already-running loopback endpoint, preserved the browser process and existing tabs, and opened/closed bridge tabs in that context.
- **Project chat creation, rename, and deletion:** PASS through the `create-chat`, `rename-chat`, and `delete-chat` CLI commands for a unique disposable `bridge-validation-` chat. The Project and ordinary Chat surface were verified; rename matched the saved conversation ID and exact title, and deletion verified sidebar removal and that the prior locator became inaccessible before removing local metadata. A repeated delete after provider-side removal is safe.
- **Response wait:** PASS after updating the observer for ChatGPT's current assistant message-body attribute. The bridge correlated the visible answer with the saved request ID, role slot, active generation/session, and exact SHA, then validated the result envelope. A separate timeout test confirms fail-closed behavior and includes the last observer state.
- **Visible response formatting:** PASS for the disposable request: the visible answer used the concise typed result envelope without progress narration. This is prompt-level formatting only; the bridge does not control hidden reasoning.
- **Automated checks:** PASS, bridge suite 21/21 and full repository suite 371/371. `npm run build` also passes.

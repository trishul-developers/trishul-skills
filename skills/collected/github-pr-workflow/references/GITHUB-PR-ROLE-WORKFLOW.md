# GitHub PR role workflow

This is the reusable operating model for an Issue/PR handled by ChatGPT role chats, a local GitHub comment poller, a Codex handoff router, and a Codex orchestrator. GitHub comments, branch state, and commit SHAs are authoritative for work. The registry maps roles to chat identities; it never overrides GitHub.

## Components and ownership

| Component | Responsibility | Durable location |
|---|---|---|
| Coordinator role | Owns scope, assignments, SHA boundaries, gates, and acceptance | PR comments and Git |
| Implementor Cloud | Makes assigned source changes and returns a result to Coordinator | PR comments and Git |
| Implementor Local | Runs explicitly assigned local/Unity gates; may be an external agent | PR comments and local evidence |
| Reviewer A/B | Independently review an exact candidate SHA; do not edit code | PR comments |
| OS poller | Reads PR comments with `gh` on a schedule; detects new/edited handoffs; verifies later consumption and current registry UUID before waking router | Cursor, revision ledger, event journal |
| Handoff router | Checks the target chat, sends a minimal work message, records delivery | Per-event acknowledgment |
| Orchestrator | Owns registry, chat setup/replacement, and exception recovery | `REGISTRY.md` |

The Codex orchestrator is infrastructure, not the Coordinator role. The router is also infrastructure: it follows `NEXT_OWNER` or `ASSIGNED_TO` and does not decide whether code is accepted. Canonical roles are `COORDINATOR`, `IMPLEMENTOR-CLOUD`, `IMPLEMENTOR-LOCAL`, `REVIEWER-A`, and `REVIEWER-B`. Historical names such as `IMPLEMENTOR-1` and `REVIEWER-1A` may be recognized when reading older comments; new handoffs use canonical names.

## Setup for another Issue/PR

1. Put the generic role contracts in the ordinary ChatGPT project's Sources. Create role chats in the user's normal ChatGPT profile, not through the `chatgptWorkCloud` task target. A short setup message contains its role, repository, Issue, PR, corresponding Project Sources, and that GitHub is authoritative. Name chats `Issue <number> - <ROLE>`. Keep UUIDs out of GitHub handoffs. If normal-chat creation is unavailable to the orchestrator, the user creates the chats in ChatGPT and the orchestrator registers their verified IDs; never silently substitute Work tasks.
2. Create or update a registry with the Issue, PR, canonical role, exact chat name, real UUID, status, last known handoff, role version, and replacement history. Obtain UUIDs from chat creation/discovery; use `UNKNOWN` until verified. Mark any outside agent as external rather than inventing a ChatGPT session.
3. Create a JSON poller config with `workspace`, `repository`, `issue`, `pr`, `trusted_authors`, `external_roles`, `registry`, `state_prefix`, `orchestrator_thread`, and optional `result_timeout_hours`. Point one OS scheduled task at the generic `pr_handoff_router_poll.py --config <file>`. Scheduling is local to the OS; do not create a ChatGPT automation for routine polling.
4. Create one low-cost Codex router chat. Bootstrap it once with this document and `HANDOFF-ROUTER.md`, then record its real UUID as `ROUTER_THREAD:` in the registry. Give the stable orchestrator `ORCHESTRATOR.md` and this document. The orchestrator is the sole registry writer.
5. Start from the live PR's latest durable handoff. Reconcile any existing event/acknowledgment state before sending a role message. Do not replay old assignments merely because a new chat was created.

## Normal path

1. A role posts one structured PR comment with a handoff identifier, `STATE`, `ASSIGNED_TO` and/or `NEXT_OWNER`, branch, relevant SHA, scope, evidence, and concise `NEXT_ACTION`. It rereads GitHub to verify the post before claiming completion.
2. The OS poller uses `gh` to inspect trusted PR conversation comments. Idle polls use no model. It keeps a scan cursor, recent body revisions, and an event for each new or edited handoff. A body edit can create a new revision event even when the comment ID stays the same. An external role event is recorded without waking a ChatGPT chat.
3. Before any model wake, the unsandboxed poller checks live GitHub for a **later result by the target role** that consumes the handoff and verifies the current role UUID in the registry. The handoff comment never counts as its own consumption. If already consumed or superseded by an edit, it records `SKIPPED` without a model turn. If GitHub or routing identity cannot be verified, it records `BLOCKED` and alerts the orchestrator.
4. For a ready event the poller queues a short message containing only the event key, target UUID and role, acknowledgment path, and router workflow path. It does not resend the procedure, role contracts, comment body, registry, or PR history. Idle polls and periodic chat health checks use no model.
5. The router checks the acknowledgment and target chat status. If usable, it sends exactly `check PR and continue` to the registered UUID, then atomically writes `DELIVERED` with the UUID and Unix delivery timestamp. The role chat rereads its Project Sources and live GitHub, performs one role turn, posts and verifies its result, then stops. The next durable comment starts the next event.

Typical source chain: `COORDINATOR → IMPLEMENTOR-CLOUD → COORDINATOR → REVIEWER-A → REVIEWER-B (if dual review is required) → COORDINATOR`. An explicit local execution gate is `COORDINATOR → IMPLEMENTOR-LOCAL → COORDINATOR`. Reviewer A may return directly to Coordinator when dual review is not required. Exact SHA and additive history requirements live in the role contracts and PR handoff, not in the router.

## Failure and recovery

- A role-chat `systemError` always produces an orchestrator alert, even if the role may have posted a PR result. The router keeps checking comments and independent events. The orchestrator checks GitHub: if the result exists, normal routing continues; otherwise it replaces the unusable chat, records the real new UUID, and retries the still-pending handoff once.
- A `DELIVERED` acknowledgment means the message reached the chat interface; it is not a completion verdict. In Issue 26, a Coordinator wake for ISSUE26-077 appeared as a user-only completed turn with no assistant response. On a stall report or timeout, check GitHub and that chat turn. If no durable result exists, retry the same chat once and record the attempt; escalate to orchestrator replacement if it still produces no answer. Routine polling does not spend model turns checking every delivered chat.
- A missing/retired/unknown UUID is `BLOCKED`. The orchestrator creates or identifies a usable chat and updates the registry. Chat replacement does not alter a GitHub handoff or SHA.
- An event left unacknowledged for 15 minutes alerts the orchestrator. A new delivered event with no later durable target-role result after the configured timeout also alerts it once. Consecutive poller errors alert it. The orchestrator checks the task, event journal, acknowledgments, registry, chat status, and live PR before recovery.
- The router's `DELIVERED`, `SKIPPED`, and `BLOCKED` acknowledgments are per event revision. A mistaken acknowledgment may be corrected only after checking live GitHub and the destination chat; record the corrected state atomically. Never send twice just because a queue message is retried.
- A role result that was posted but whose chat ended in error is still durable if verified on GitHub. The router must continue to its `NEXT_OWNER`; a chat error never erases the PR result.
- Keep routine queue messages and router responses short. The router does not read PR comments during normal delivery; the local script and role chat each verify GitHub at their respective boundaries. When the router chat reaches a context or system limit, the orchestrator replaces it and updates `ROUTER_THREAD`; the new chat resumes from journal and acknowledgments. Avoid routine chat creation or compaction when the router remains healthy.

## Issue 26 / PR 28 example

The repository is `tosumitdhaka/Ukrainian-Warfare`; the registry is `.agents/state/REGISTRY.md`; the config is `.agents/state/pr28_router_config.json`; state lives under `Logs/pr28_comment_router.*`. The Windows task invokes `scripts/pr28_router_poll.py`, which delegates to the generic poller. ChatGPT role titles use `Issue 26 - COORDINATOR`, `Issue 26 - IMPLEMENTOR-CLOUD`, `Issue 26 - REVIEWER-A`, and `Issue 26 - REVIEWER-B`. `IMPLEMENTOR-LOCAL` is Antigravity outside ChatGPT and auto-consumes its GitHub assignment, so it has no role-chat wake. The earlier Issue 26 role chats were created through the Work cloud task path and retained in registry replacement history. User-created ordinary ChatGPT chats are now the active UUIDs. The poller can be paused with `routing_enabled:false` and a disabled Windows task; while paused it exits `ROUTER_PAUSED` without querying GitHub or waking a model.

ISSUE26-060 illustrates edited-comment handling: a Coordinator comment originally named the historical `IMPLEMENTOR-1`; its owner fields were corrected in place to `IMPLEMENTOR-CLOUD`. The poller now detects that body revision. The cloud implementor posted an exact-SHA result; Coordinator assigned ISSUE26-061 to Reviewer A. Reviewer A posted `CHANGES_REQUIRED` with `NEXT_OWNER: COORDINATOR`. That Reviewer A comment is the *input* to Coordinator, not evidence that Coordinator consumed it. The router checks for a subsequent Coordinator result before deciding whether to send. This example describes routing behavior, not an accepted code verdict or a permanent current PR status.

## Files

- `HANDOFF-ROUTER.md`: executable router behavior and acknowledgment rules.
- `ORCHESTRATOR.md`: chat lifecycle, registry ownership, and exception recovery.
- `.agents/skills/github-pr-comment-watcher/scripts/pr_handoff_router_poll.py`: reusable poller.
- `.agents/skills/github-pr-comment-watcher/SKILL.md`: CLI and skill usage.
- `REGISTRY.md` and per-Issue/PR JSON config: operational data, not generic role contracts.

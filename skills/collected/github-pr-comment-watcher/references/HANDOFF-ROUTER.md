# Handoff Router

The router delivers durable GitHub role handoffs for one configured Issue/PR. It uses the cheapest suitable model. The local poller wakes it only for an actionable handoff or an exception. There is no periodic model health check.

The poller's routine wake message carries only an event key, target UUID and role, acknowledgment path, and this file. The unsandboxed local poller has already verified the live GitHub handoff, later target-role consumption, and registry UUID. Do not repeat GitHub reads or dump the event journal, registry, or PR conversation into the chat. The role chat independently rechecks GitHub before acting, which covers a result posted between poller preflight and delivery.

Roles listed as `external_roles` in the poller config are handled by an outside agent that reads GitHub itself. Do not create or message a ChatGPT chat for such a role. The Issue #26 `IMPLEMENTOR-LOCAL` role is owned by Antigravity and auto-consumes its GitHub assignments.

## Handoff delivery

1. Read only the acknowledgment path in the wake message. If it is already `DELIVERED` or `SKIPPED`, stop. The target UUID in the wake came from the current registry during the poller's GitHub preflight; do not use a remembered UUID.
2. Inspect that target UUID's chat status. If usable, send exactly `check PR and continue` to that existing chat and atomically write `{"status":"DELIVERED","target_uuid":"<verified UUID>","delivered_at":<Unix seconds>}` to the specified `ack_path`. `delivered_at` enables a one-time timeout alert if the role never posts a durable result. Do not perform a second GitHub check in this routine turn.
3. If the chat is unusable, write `BLOCKED` and notify the orchestrator with the role, UUID, event key, and status. A `systemError` always triggers this notification, even when a PR result may exist. The orchestrator checks GitHub and replaces chats as needed.
4. Keep other independent events moving. The router does not post PR comments, decide scope, or create chats.

Keep routine responses to one short status line. Store delivery status in the acknowledgment file, not in a long chat recap. If this router chat reaches a context or system limit, notify the orchestrator; it replaces the chat and updates `ROUTER_THREAD` without changing GitHub state.

## Recovery

- The poller alerts the orchestrator once when a delivery remains unacknowledged or a newly delivered handoff has no durable target-role result beyond the configured timeout. These alerts replace periodic model health checks. Legacy acknowledgments without `delivered_at` do not start a timeout alert.
- `DELIVERED` proves only that the message-send call succeeded. It does not prove that the role chat generated an answer or posted a PR result. On a stalled-handoff alert, inspect the target chat and live GitHub. If the chat has only the incoming user message and no assistant answer, and GitHub has no durable result, retry that same role chat once and record the retry time in the acknowledgment or orchestrator notes. If the retry also produces no answer, mark the handoff blocked and let the orchestrator replace or repair the chat. Do not send repeated wake messages on a timer.
- The orchestrator owns chat creation/replacement and registry edits. On its explicit retry request, recheck GitHub and the per-comment acknowledgment before sending again.
- Do not edit the poller's scan cursor or event journal. Do not post PR comments, make Coordinator decisions, or create schedules or automations.

## Role names

Canonical roles are `COORDINATOR`, `IMPLEMENTOR-CLOUD`, `IMPLEMENTOR-LOCAL`, `REVIEWER-A`, and `REVIEWER-B`. The poller may normalize old comment names for continuity. New GitHub handoffs use canonical roles.

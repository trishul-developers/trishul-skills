# Workflow Orchestrator

The orchestrator manages chat identity and recovery for an Issue/PR. It is not a GitHub workflow role. GitHub comments and live branch state remain authoritative for work; the local registry is routing metadata.

## Inputs

Each invocation supplies the repository, Issue, PR, registry path, poller config path, and router chat identity. Use the role contracts already available in the ChatGPT project when bootstrapping role chats. Do not copy entire contracts into each chat.

## Responsibilities

1. Be the sole operational writer of the registry. Resolve actual chat UUIDs from chat discovery or creation; never guess. Keep one preferred healthy chat per canonical role and preserve replaced rows.
   Name each role chat `Issue <issue> - <CANONICAL-ROLE>` when its real UUID is available, and keep the registry's Chat Name column identical to the verified app title. Name infrastructure chats `Issue <issue> - ORCHESTRATOR` and `Issue <issue> - HANDOFF-ROUTER`. Keep PR identity in registry metadata, not the chat title. Rename setup-only chats before registering them. Do not encode a session number or transient status in the title.
2. Keep the `ROUTER_THREAD:` registry entry current. The router chat may be replaced; the orchestrator chat is the stable recovery contact.
3. On every router report of `systemError`, record the alert even if the role may already have completed. Reconcile the expected result against durable GitHub comments. If it exists, allow normal next-owner routing. If absent and the chat is unusable, replace the chat and arrange one retry of the pending handoff.
   Also treat a completed chat turn containing only the incoming user message and no assistant response as an execution failure, even when the router acknowledgment says `DELIVERED`. Check GitHub first; if no durable result exists, retry the same healthy chat once and record that retry. Replace or repair it if the retry likewise produces no result.
4. On an unacknowledged router event or failed router health check, inspect the event journal and acknowledgment first. Replace the router when needed, update its UUID in the registry, and resume pending events without duplicate delivery.
5. Treat roles listed as `external_roles` in the poller config as outside agents, not ChatGPT sessions. For Issue #26, `IMPLEMENTOR-LOCAL` is Antigravity on the local setup and auto-consumes GitHub assignments. Keep its chat UUID `UNKNOWN` and do not create or wake a ChatGPT substitute. Verify its execution evidence from GitHub when required.
6. Create replacement role chats in the user's ordinary ChatGPT profile. Do not use the `chatgptWorkCloud` creation target for routine role chats: Issue #26 role chats made through that target consumed the Work task quota. If this environment cannot create an ordinary ChatGPT chat, record the role as awaiting a verified personal-chat UUID and ask the user to create it through the normal ChatGPT interface. Never silently substitute a Work task. Do not wake existing Work role chats while the cost migration is pending.

## Boundaries

- Do not act as Coordinator, Implementor, or Reviewer; do not decide acceptance or change the assigned SHA.
- Do not poll GitHub on a timer. The local script detects comments; the router handles routine handoffs. Read GitHub when resolving an exception.
- Do not create ChatGPT automations, schedules, or Publisher tasks.
- Create replacement chats with setup-only role/repository/Issue/PR/Project Source context. Send a work message only after the real UUID is verified and the pending handoff still exists.
- Keep the registry and router configuration in sync. A chat UUID change never changes a GitHub role name or handoff.

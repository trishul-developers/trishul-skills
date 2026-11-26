# Phase brief: {{phase}}, {{title}}

From: manager. To: the {{phase}} orchestrator. You are this skill's driver for the phase.

## What the owner decided
{{owner_decisions}}

## Contacts
- Phase architect: `{{architect_session}}`. Send it rulings and questions directly, by session id.
- Manager (the session that started you): owner gates (merges), blockers, the phase-end report, and anything that needs the owner. Don't relay through the manager what the architect can answer.

## The skill
- Read the `agent-delivery` skill's `SKILL.md` first. Run the script with `-C {{repo_dir}}` (the main checkout, never a worktree), so there is one run log.
- Start with `roles -v` and `status`. Models come from the user config; don't copy model names from older briefs.

## The phase
- Spec: {{spec_ref}}. Architect state: {{architect_state_ref}}.
- Base: `{{base}}` at `{{base_sha}}`.
- Queue, in order. Each item is one batch, on one branch, in one worktree, with one PR:
{{queue}}
- Owned paths and exclusions: {{paths}}
- Known risks and carried items: {{carried}}

## The loop, for each batch
1. Ask the architect your open questions first. Don't block on the answers: brief on your proposed defaults and fold in the rulings when they arrive.
2. Run `brief implement` with `worktree` set, then `run implementor` (or `maths-implementor` for steps flagged maths). For a native slot, start the subagent; when it returns, log it with the `done` command the script prints.
3. Judge: a fresh, non-zero test run with the project's filters; the diff stays in owned paths; any pin move has a differential note.
4. Run `brief review`, then `run reviewer --implemented-by <family>` (`reviewer-light` for Tier 2 and 3). Run it in the background. On blockers, the implementor fixes, then run `brief recheck` and `run reviewer --resume <thread>` on the same thread. If it still fails after 2 rounds, tell the manager.
5. Land: push and wait for green CI. Open the PR with scope, test counts, the differential note, and the reviewer's verdict, model and thread. Run `log verdict`. Then send the manager the PR number and a one-line reason. The manager gets the owner's merge and tells you, so you can `log merge`.

## Phase end
Run the phase review (`phase-reviewer`) from `{{base}}` to head, assemble the evidence, and send the manager the report with the four numbers: steps closed, fix rounds, CI runs, and architect questions. The architect records acceptance.

## Rules
{{rules}}

# Phase review: {{phase}}

You are the independent phase reviewer. You start fresh. Do not edit files.

## Scope
- Repository `{{repo_dir}}`. Base tag `{{base}}`, head `{{head}}`.
- Spec: {{spec_ref}}. Evidence: {{evidence_ref}}. Phase list (deferred should-fix items): {{phase_list_ref}}.
- Read the Tier 1 files changed in `git diff --stat {{base}}...{{head}}` closely: {{tier1_paths}}. Skim the rest only where the phase list points.

## Check
- Every spec acceptance check has evidence (a test, a CI job, or a recorded owner check).
- Authority, knowledge leaks, stale handles, scheduling races, snapshot and hash coverage of new state, replay and save/restore.
- Phase-list items: still acceptable to defer, or now blocking?

## Blockers (only these)
A defect a player can hit; a replay or save/restore break in a normal run; an outcome pin move with no named cause.

## Output
### Phase verdict: PASS | CHANGES_REQUIRED
#### Findings (BLOCKER / SHOULD-FIX / NIT, with file:line, scenario, citation, action)
#### Acceptance checks: one line each, met / not met / not evidenced
#### Not checked

If you are close to running out of quota, post a partial verdict with what you covered rather than nothing.

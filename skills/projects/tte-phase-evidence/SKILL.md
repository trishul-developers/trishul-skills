---
name: tte-phase-evidence
description: Assemble the phase-end review package for the architect (step table, CI links, empty red list, differential report, capture, state-inventory diff, deviations). Use when all steps of a phase are done and you must request review. Orchestrator role.
---

# Phase-end evidence package (orchestrator)

Format source: `docs/implementation/review_protocol.md` ("Required implementor handoff") and plan v2 section 4. The orchestrator cannot accept a phase; it requests review in **one issue comment** and tells the owner in one line.

## Preconditions (check, do not assume)
- Every step checkbox in the phase issue is ticked and each has a commit.
- **CI green on the PR head:** `gh pr checks <pr>`; EditMode and PlayMode both pass (`gh run list --workflow unity-ci.yml --branch <branch> --limit 3`).
- **Red list empty:** the phase's `*_temporary_red_list.md` has no entries and was deleted; no test outside it was ever left red.
- No `HOLD(Qn)` markers and no `NotImplementedException`/TODO in the diff (`git grep -n "HOLD(Q\|NotImplementedException\|TODO" -- Assets/Scripts`).
- Open architect questions for the phase are all answered (issue comments); amendments are in the spec.

## Assemble (all links, no pasted logs)
1. **Step table:** step id -> commit SHA -> test class(es) -> result (one row per step; `git log --oneline origin/main..HEAD`).
2. **CI evidence:** run URL, EditMode/PlayMode counts (`python -I ci/test-summary.py`), and the artifact names.
3. **Acceptance checks:** the spec's numbered checks, each with the test name that proves it.
4. **Differential report** if the ruleset changed (skill `tte-golden-recapture`): attach the generated file.
5. **Capture:** a short scene capture or screenshot for visible phases (executor).
6. **Benchmark artifact** for phases that require one (IL2CPP player at milestones only).
7. **State inventory diff:** `git diff origin/main...HEAD -- docs/implementation/state_inventory.md`, summarised as new authoritative state with writer and section.
8. **Deviations:** every deviation from the spec with its reason; every amendment applied; every `PINS Qn` answered.
9. **Review depth by tier:** tier 1 full diff review; milestones also need the owner play-check (prepare a 5-line play script).

## Request
Post the package as one comment on the phase issue ("READY_FOR_REVIEW: <phase>") with the links above, set the PR to ready, and tell the owner in one line. **Stop at the review boundary**: do not start the next phase until the architect records `ACCEPTED`.

---
name: tte-batch-review
description: Lean batch-review procedure for TTE reviewers and orchestrators. Enforces one joint review of tests and code together, a single recheck of changed items only by the same reviewer, strict blocker criteria (player-facing, replay/save-state breakage, or unexplained outcome pin moves), differential note validation, and standardized verdict reporting.
compatibility: Platform independent. Markdown instructions only.
tags: [tte, review, reviewer, orchestrator, lean-process]
---

# TTE Lean Batch Review

This skill defines the authoritative, single-pass batch-review procedure established in `decision_lean_process_2026-11-05.md` and `workflow.md`. Its goal is to eliminate review round-trips and speculative blocking while strictly defending player experience and simulation determinism.

---

## 1. Single Review Pass & Same-Reviewer Recheck
- **One Joint Review**: Review acceptance tests and production code together at the end of the batch. There is **no separate test review**.
- **One Recheck Only**: If changes are required, the **same reviewer** re-checks only the modified items in a single follow-up pass.
- **Independence**: A reviewer never reviews their own code.

---

## 2. Strict Blocker Criteria
Only the following three categories constitute a **BLOCKER** that stops a merge (`CHANGES_REQUIRED`):

1. **Player-Facing Bug**: A defect that a player can actually hit in normal gameplay or tactical control.
2. **Replay or Save/Restore Breakage**: A divergence in simulation replay identity or save/restore state during a normal run.
3. **Unexplained Outcome Pin Move**: A simulation outcome pin change that has no named spec step or architect ruling in the differential note.

> [!IMPORTANT]
> **Everything else goes on the phase list.** Findings regarding secondary edge cases, naming, non-allocating refactors, comment clarity, or future debt are classified as non-blocking and recorded on the phase issue list for whole-phase review.

---

## 3. Differential Note Check
Every batch that recaptures or baselines simulation pins must include a differential note table:

| Pin | Class | Cause |
|---|---|---|
| `<pin_name>` | `layout`, `new state`, or `outcome` | `<spec step or #64 ruling>` |

- **Verification requirement**: The reviewer must check that every **outcome** move explicitly cites the governing spec step or architect ruling (e.g. `#64 Q36`, `spec §4.2`).
- An outcome move citing "expected", "various fixes", or lacking a specific spec/ruling citation is a **BLOCKER**.

---

## 4. Standard Review Output Schema
The reviewer must structure their review response using this exact schema:

```markdown
### Batch Review Verdict: [PASS | CHANGES_REQUIRED]
- **Reviewed Head SHA**: `<40-character commit SHA>`
- **Batch Steps**: `<e.g. G02.08–G02.10>`
- **Differential Note Checked**: [YES | N/A]

#### Findings
1. **[BLOCKER | PHASE-LIST]** `<file>:<line>`
   - **Failing Scenario**: `<concrete reproducer or scenario>`
   - **Spec / Ruling Citation**: `<spec clause, D-doc section, or #64 ruling>`
   - **Required Action**: `<exact fix required>`

#### What Was Not Checked
- `<explicit list of untouched subsystems, platforms, or unexecuted workloads>`
```

---
name: pr-handoff-lifecycle
description: >-
  Use this skill to draft, validate, and verify PR role handoffs ([IMPLEMENTOR-1], [COORDINATOR], [REVIEWER-1A/B]) directly from git history, diffs, and NUnit test report XMLs.
---

# PR Handoff Lifecycle Automation

This skill automates the creation and verification of structured role handoffs as mandated by `AGENTS.md` and `docs/implementation/review_protocol.md`.

## Key Roles & Workflow

```
[COORDINATOR] (Assigns work, sets START_SHA & scope)
      │
      ▼
[IMPLEMENTOR-1] (Implements, tests, drafts handoff with FINAL_SHA & test evidence)
      │
      ▼
[COORDINATOR] (Validates routing preconditions: ancestry, ahead/behind, PR HEAD)
      │
      ▼
[REVIEWER-1A / 1B] (Evaluates 6-point checklist, returns SOURCE_REVIEW_PASS)
```

---

## Commands & Usage

Helper script path:
`.agents/skills/pr-handoff-lifecycle/scripts/handoff.py`

### 1. Draft Implementor Handoff
Generates the exact 15-field `[IMPLEMENTOR-1]` markdown block from git commits, diffs, and test report XML:

```powershell
python .agents/skills/pr-handoff-lifecycle/scripts/handoff.py draft-implementor `
    --assignment-id ISSUE26-009 `
    --start-sha f567b02027dbf31c96ee4382eb4158516c378ddd `
    --tests-xml Logs/issue26-009-f01.xml `
    --output scratch/implementor_handoff.md
```

Then publish to PR using the GitHub PR skill:
```powershell
python .agents/skills/github-pr-workflow/scripts/gh_helper.py comments post --pr 28 --file scratch/implementor_handoff.md
```

### 2. Verify Candidate Routing (Coordinator Pre-flight)
Validates that the candidate commit is an exact additive descendant of `START_SHA` (`ahead >= 1`, `behind == 0`):

```powershell
python .agents/skills/pr-handoff-lifecycle/scripts/handoff.py verify-candidate `
    --start-sha f567b02027dbf31c96ee4382eb4158516c378ddd `
    --candidate-sha e4ebe4748f7e43840e5a170184092a23dfb6ffd9
```

### 3. Draft Coordinator Routing Handoff
Drafts the canonical assignment handoff for reviewers:

```powershell
python .agents/skills/pr-handoff-lifecycle/scripts/handoff.py draft-coordinator `
    --handoff-id ISSUE26-011 `
    --candidate-sha e4ebe4748f7e43840e5a170184092a23dfb6ffd9 `
    --baseline-sha f567b02027dbf31c96ee4382eb4158516c378ddd `
    --consumes "ISSUE26-009 final [IMPLEMENTOR-1] result" `
    --assigned-to REVIEWER-1A `
    --also-assigned-to REVIEWER-1B `
    --dual-review `
    --branch fix/issue-26-phases-05-09-remediation `
    --scope "Review only F01 regression remediation" `
    --output scratch/coordinator_handoff.md
```

### 4. Draft Reviewer Verdict
Drafts the 6-point checklist verdict:

```powershell
python .agents/skills/pr-handoff-lifecycle/scripts/handoff.py draft-reviewer `
    --role REVIEWER-1A `
    --handoff-id ISSUE26-011 `
    --candidate-sha e4ebe4748f7e43840e5a170184092a23dfb6ffd9 `
    --verdict SOURCE_REVIEW_PASS `
    --output scratch/reviewer_handoff.md
```

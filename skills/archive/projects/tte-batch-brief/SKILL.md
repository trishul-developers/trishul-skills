---
name: tte-batch-brief
description: Concise template and guidelines used by the project manager to brief an orchestrator for a 2-4 step work batch. Defines base branch & SHA, step table with risk tier and model, governing rules, carried-forward phase-list items, reporting requirements, and wait/idle boundaries.
compatibility: Platform independent. Markdown template only.
tags: [tte, brief, manager, orchestrator, planning]
---

# TTE Batch Brief Template

This skill provides the standard, concise template used by the Project Manager to brief an Orchestrator (`orchestrator-codex` or `orchestrator-claude`) for an execution batch under the lean process (`workflow.md` §4).

---

## Batch Brief Template

```markdown
# Batch Brief: [Phase].[Batch] (e.g. G02.08–G02.10)

## 1. Identity & Base
- **Target Phase Branch**: `g02-presentation-orders-ux`
- **Base Commit SHA**: `<verified remote phase head SHA>`
- **Working Branch**: `<e.g. g02-08-10-impl>`

## 2. Steps & Assignments
| Step | Description | Risk Tier | Model & Effort | Subagent Role |
|---|---|---|---|---|
| `<Step ID>` | `<Step description from spec>` | Tier 1 | Sol, medium | Implementor |
| `<Step ID>` | `<Step description from spec>` | Tier 2 | Terra, high | Implementor |
| `<Step ID>` | `<Step description from spec>` | Tier 3 / Docs / Execution | Luna | Light Worker |

*Assignment follows `workflow.md` §2: Tier 1 implementation is Sol medium, Tier 2 and 3 implementation is Terra high, and light tasks/docs/execution are Luna. If Codex is out of quota, the fallback is Sonnet high (or Haiku for light tasks).*

## 3. Governing Invariants
- **Tests First**: Acceptance tests written first; reviewed together with code (no standalone test review).
- **Settings Guard**: Never commit or modify `ProjectSettings/**` or `Packages/**`.
- **Differential Note**: Re-baseline simulation pins at batch end only, with an explicit cause citing a spec step or architect ruling for every outcome move.
- **Blockers Only**: Only player-facing defects, replay/save breaks, or unexplained outcome pin moves block. All others go to the phase list.
- **Attribution**: No AI attribution trailers (`Generated with`, `Co-Authored-By`) anywhere (owner rule).

## 4. Phase-List Items Carried Forward
- [ ] `<Item 1 from previous batch review / issue comments>`
- [ ] `<Item 2 from previous batch review / issue comments>`

## 5. What to Report
On completion, the orchestrator reports:
1. Verdict: `PASS` or `CHANGES_REQUIRED`
2. Final Commit SHA: `<40-char SHA>`
3. Verification: FastCompile, EditMode, and PlayMode test counts
4. Differential Note table (if pins moved)
5. Out-of-scope / Unverified items

## 6. When to Wait (Idle Rules)
- **Wait (`inbox_wait`)**: ONLY while an outside party owes a reply (e.g. architect ruling on #64, cross-provider review, or owner decision).
- **End Turn**: While native subagents run or after completing the batch and posting the report. Do not poll or hold empty loops.
```

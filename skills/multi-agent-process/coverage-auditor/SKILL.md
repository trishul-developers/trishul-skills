---
name: coverage-auditor
description: Audit pull requests, diffs, and codebase state with rigorous coverage accounting. Enforces the strict rule that reviewers must explicitly categorize reviewed files into 'Read in Full', 'Grep / Signature Checked', and 'Unread / Out of Scope', and strictly bans claiming unread areas are sound.
compatibility: Platform independent. Works with git diffs, PRs, or file lists.
tags: [review, audit, coverage, quality, pr-verification]
---

# Review Coverage Auditor

This skill enforces integrity in code and architecture reviews. It eliminates "lazy approvals" and unwarranted generalizations by requiring agents to explicitly declare the depth of inspection for every file touched in a change set.

## The Core Rule of Review Coverage
> [!CAUTION]
> **Never imply that unread or lightly-scanned areas are sound.**
> Every review finding or approval must explicitly disclose its scope. If a file was not read line-by-line, state so clearly.

## Review Coverage Taxonomy

Every file touched by a changeset must be classified into one of three tiers:

### 1. `READ_IN_FULL` (Line-by-Line Inspection)
- The entire file or diff hunk was read and analyzed in context.
- Logic, edge cases, error transitions, concurrency, and memory allocations were verified.
- Soundness claims are permitted for this tier.

### 2. `GREP_CHECKED` (Interface / Call-Site Verification)
- The file was inspected via symbol grep, type signatures, or public API declarations only.
- Internal control flow, thread safety, and private helper logic were **NOT** verified.
- Claims are strictly limited to interface compatibility.

### 3. `UNREAD_OUT_OF_SCOPE` (Unexamined Files)
- The file was touched (e.g. formatting, assets, generated code, migrations) but not reviewed in detail.
- **Explicit Invariant**: Must be explicitly marked as *Unverified*. No statement may imply this file is correct, safe, or bug-free.

## Standardized Review Coverage Report

```markdown
### CODE REVIEW & COVERAGE AUDIT
- **Target SHA:** `8d0ba39f`
- **Reviewed By:** Reviewer-Claude (claude-3-7-sonnet / high)

#### Coverage Inventory
| File Path | Coverage Tier | Lines Examined | Notes |
|---|---|---|---|
| `Assets/Scripts/Combat/CombatManager.cs` | **READ_IN_FULL** | 1–340 | Verified tick loop and allocation bounds. |
| `Assets/Scripts/Contracts/ICombatService.cs` | **GREP_CHECKED** | 1–45 | Verified method signatures and parameter types. |
| `Assets/Prefabs/Units/TankT90.prefab` | **UNREAD_OUT_OF_SCOPE** | — | Unity binary/YAML asset; unverified. |

#### Findings
- **[BLOCKING]** `CombatManager.cs:182`: Allocates `new List<EntityId>()` inside the per-tick update loop. Violates zero-GC invariant.
- **[NIT]** `CombatManager.cs:42`: Redundant namespace import.

#### Soundness Statement
Coverage was achieved for the combat management logic only. Unity prefab linkages and asset serialization were **UNREAD** and remain unverified.
```

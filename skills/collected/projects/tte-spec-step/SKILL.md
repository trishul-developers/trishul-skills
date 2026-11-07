---
name: tte-spec-step
description: The test-first loop for implementing a phase spec step batch in this project (read the file list, write failing tests, compile, implement, update the red list, hand off). Use when assigned steps such as G01.04-G01.06. Implementor role.
---

# Spec step batch (implementor)

Authority: AGENTS.md > engine_architecture_v4.0.md > D1-D8 > plan v2 > the spec (including its amendments). A spec gap that is **local, reversible and tier 2/3** (naming, enum values, error codes following an existing pattern, test-only structure, capacity defaults, 'lowest id first' tie-breaks) you may decide: log it in the PR description decision-log table (step, decision, why local/reversible, file:line). A gap touching **authority, determinism/hashing, knowledge leaks, scope or player-facing behaviour** is **not yours to decide**: stop that item, quote the passage, propose a default in your report, continue with the rest. Two failed fix rounds on one problem: stop and post evidence (failing test, about 50 log lines, diff summary).

## Loop
1. **Read narrowly:** AGENT_BRIEF.md, the spec sections for your steps (and its amendments), only the design sections it cites, `docs/implementation/state_inventory.md`, and the existing code the step touches. Do not read the whole repo.
2. **Branch/worktree:** work only in the assigned branch/worktree. Stage files **by explicit path**; never `git add -A` (Unity rewrites ProjectSettings/*.asset and URP settings; never commit that churn).
3. **Tests first (stage 1):** write the spec's checks as failing tests plus only the minimal compile surface (pure data contracts are real code; behaviour stubs that throw are temporary and listed in your report). Include negative, corruption/truncation, determinism (two runs identical) and save/restore continuation tests. Tag any test that pins a choice the spec leaves open with `// PINS Qn`. Run only your new classes (skill `tte-unity-test`): they must be red for the right reason with 0 compile errors. Commit, push, **stop** for the test review.
4. **Implement (stage 2) after the tests are approved:** batches of 2-4 steps. After each edit batch run `dotnet build ci/FastCompile/FastCompile.csproj --configuration Release --nologo` (0 errors, 0 warnings). One focused Unity run per batch.
5. **Rules that reviewers check:** deterministic (no UnityEngine.Random, stable ordering, no hash-map iteration order); single writer per state group; new authoritative state goes into the snapshot **and** the canonical hash **and** `state_inventory.md`; never silently drop work (bounded, diagnosed failure); 0 managed allocations on steady-state hot paths; no stubs, TODOs or NotImplementedException in finished code; no edits outside the slice.
6. **Red list:** `docs/implementation/plan_v2/G01_temporary_red_list.md` (per phase) names every existing test that is expected to be red and why. Any red test outside it is a defect. The list only shrinks; it must be empty before the review request.
7. **Report (under 40 lines):** commit SHA(s); counts per Unity run; remaining reds vs the red list; decisions you had to take (should be none); open questions with quotes; state_inventory entries added.

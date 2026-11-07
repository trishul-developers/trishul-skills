---
name: tte-golden-recapture
description: Recapture golden hashes after a deliberate ruleset or layout change, behind the FreeForAll projection-equality check, and generate the differential report. Use at G01.13 and after every ruleset change. Implementor role.
---

# Golden recapture (implementor)

A golden is recaptured only when the change is **deliberate** (new authoritative state, section, ruleset bump). A golden that changes for any other reason is a regression: stop and report. **Never edit a golden by hand**; the tools below rewrite the pinned lines from a Unity run and refuse to move anything that is not a snapshot-byte digest.

Pieces (all under `ci/` and `Assets/Tests/EditMode/Projection/`):
- `FfaProjection.cs`, `FfaScenarios.cs`, `FfaProjectionEqualityTests.cs`: the projection harness. A *projection* drops everything the change added (new fields, new sections, renumbered handles) and compares DOMAIN outcomes: every section the change did not touch by payload hash, Combat / TacticalAI / Perception / Comms through their read API with `ContactRef` replaced by the contact identity.
- `ci/ffa-baseline/`: the reference captured at the merge-base commit (`BASE_COMMIT`): `pre-g01-traces.txt` (per-tick digests of the whole-session scenarios), `pre-g01-pins.txt` (projection pins hooked into the golden kits), `g01-expected.txt` (the recorded comparison at the new head), `capture-pre-g01.ps1`, `kit-hooks.patch`, `FfaProjectionLayout.pre-g01.cs`.
- `ci/golden-recapture.py`: rewrites pinned `GOLDEN|` lines from `golden-actual.txt` with a review gate per kit.
- `ci/g01-differential-report.py`: writes `docs/implementation/reviews/G01-ruleset-differential.md` (deterministic; `--check` fails when stale).

## Procedure
1. **List the reds:** the phase red list (`docs/implementation/plan_v2/G01_temporary_red_list.md`) names every golden expected to change and why. Anything else changing is a defect.
2. **Reference first (pre-change behaviour):** create a second checkout of the merge-base (`git worktree add --detach ../ref-pre-g01 <BASE_COMMIT>`, copy a `Library` folder into it) and run `powershell -File ci/ffa-baseline/capture-pre-g01.ps1 -Ref ../ref-pre-g01`. It applies `kit-hooks.patch`, copies the harness with the pre-change layout file, runs the projection and golden classes (they must be fully green there) and rewrites `pre-g01-traces.txt` and `pre-g01-pins.txt`. Never run two Unity instances at once on one package cache; run them one after the other.
3. **Projection equality (FreeForAll):** at the new head run the harness (`-TestFilter Trishul.Tests.EditMode.Projection.FfaProjectionEqualityTests` plus the golden classes). `FfaProjectionEqualityTests` asserts, per scenario, identical per-tick digests up to the classified difference (A4 Q48: the first tick at which any entity is defeated, `CapabilityFlags == None` or a wreck; divergence may begin only after it, and a scenario that never defeats an entity must be fully equal). The kit `FfaStore.Pin` calls assert the golden-kit projections. Any other difference: STOP and report (what diverged, at which tick, which component).
   To (re)write `g01-expected.txt` set `UW_FFA_CAPTURE_DIR=<dir>` for the run and copy `<dir>/g01-expected.txt` after reviewing it. `UW_FFA_SECTIONS=1` adds per-tick section hashes and `UW_FFA_DUMP="scenario:tick,tick"` dumps checkpoints for byte-level diagnosis (diagnostic only).
4. **Recapture** only after step 3 passes: run the golden classes with `UW_GOLDEN_ACTUAL_DIR=<dir>` (every golden check writes its actual line, pass or fail), then `python ci/golden-recapture.py --actual <dir>/golden-actual.txt` for the review table (nothing written), and `--apply` to rewrite. Only the snapshot-byte digests of each kit may move (the allow-list is in the script: a hash that moved because a section or field was added is expected; a payload or outcome digest, a count or a failure code moving aborts with exit 2). A test that aborts at its first golden hides later ones, so repeat run + apply until the review table is empty. Commit the new values with the reason in the message.
5. **Differential report:** `python ci/g01-differential-report.py` and commit `docs/implementation/reviews/G01-ruleset-differential.md`; link it from the phase issue. CI should run it with `--check`.
6. **Update:** `RulesetVersion` (only if the spec says so), `state_inventory.md`, and remove the recaptured entries from the red list. The list must be empty before the review request.
7. **Verify:** run the full suite in CI (not locally) twice; both runs must show identical canonical hashes.

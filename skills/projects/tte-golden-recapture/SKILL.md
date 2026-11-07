---
name: tte-golden-recapture
description: Recapture and re-baseline golden simulation pins once per batch under the accepted G02 lean process using TTE_GOLDEN_ACTUAL_DIR and ci/golden-recapture.py with a differential note table. Implementor role.
---

# Golden Recapture & Re-baseline (`tte-golden-recapture`)

Under the accepted lean implementation process (`docs/implementation/plan_v2/decision_lean_process_2026-11-05.md`), the legacy FFA projection gate (`FfaProjection.cs`, `ci/ffa-baseline/`) is **retired**.

Golden simulation pins are re-baselined **once per batch, at batch end**, in a single clean commit accompanied by a structured differential note.

> [!IMPORTANT]
> - **Never edit a golden literal by hand.**
> - Golden lines are generated only through Unity test execution captured via `TTE_GOLDEN_ACTUAL_DIR`.
> - Re-baselining is permitted only when changes are deliberate (new authoritative state, layout adjustments, or approved ruleset amendments).
> - Accidental outcome shifts remain strict blockers.

---

## 1. What Stays vs What is Retired

- **Retired (Removed)**:
  - `FfaProjectionEqualityTests` and `FfaProjection*` harness.
  - `ci/ffa-baseline/` reference captures and `capture-pre-g01.ps1`.
  - `UW_` prefixed environment variables (`UW_FFA_*`, `UW_GOLDEN_ACTUAL_DIR`).
  - Per-step pin recapture gates.
- **Retained (Authoritative)**:
  - `ci/golden-recapture.py` inspection and rewrite gate.
  - Pinned `GOLDEN|` literals in `Assets/Tests/EditMode/`.
  - The `FreeForAll` preset and workload.
  - Deterministic replay, checkpoint, and save/restore identity tests.

---

## 2. Re-baseline Procedure (Batch End)

Execute re-baselining at the close of an implementation batch:

### Step 1: Execute Golden Tests with Capture Directory
Run the golden EditMode suites with `TTE_GOLDEN_ACTUAL_DIR` pointing to a scratch folder. Tests output their actual results to `golden-actual.txt`:

```powershell
$env:TTE_GOLDEN_ACTUAL_DIR = "scratch/golden"
New-Item -ItemType Directory -Force -Path "scratch/golden"

# Run targeted golden EditMode test suites via Unity
python "skills/unity-pipeline/scripts/unity_pipeline.py" test `
  --platform EditMode `
  --filter "Trishul.Tests.EditMode.Perception,Trishul.Tests.EditMode.Comms,Trishul.Tests.EditMode.GroundMotionStatic"
```

### Step 2: Audit Moved Pins (Dry-Run Table)
Review the diff without modifying files:

```powershell
python ci/golden-recapture.py --actual scratch/golden/golden-actual.txt
```

The script prints the review table displaying kit, pin key, moved labels, and verdict (`OK` vs `REJECTED`).

### Step 3: Apply Permitted Updates
Rewrite the pinned literals in the test source files:

```powershell
python ci/golden-recapture.py --actual scratch/golden/golden-actual.txt --apply
```

### Step 4: Construct the Differential Note Table
For every moved pin, classify the movement in the batch differential note table:

```markdown
| Pin | Class | Cause |
|---|---|---|
| `<pin_key>` | `layout` \| `new state` \| `outcome` | `<spec step or ruling>` |
```

**Classification Rules:**
- `layout`: Serialization offset or layout change due to new schema fields.
- `new state`: New authoritative state section or component added.
- `outcome`: Simulation domain outcome changed. **MUST** cite the exact spec step or architect ruling. An outcome change with no named cause is a **blocker**; the pin must NOT be recaptured.

### Step 5: Commit and Verify
1. Stage and commit test sources:
   ```powershell
   git add Assets/Tests/EditMode/
   git commit -m "test: re-baseline golden pins for batch <id>"
   ```
2. Post the differential note table to the tracking PR / phase issue.
3. Run two consecutive test passes in CI to confirm identical canonical hashes across runs (determinism gate).

---
name: sim-contract-audit
description: >-
  Use this skill to statically audit C# simulation changes and diffs for architectural invariant violations (e.g. UnityEngine.Random, Transform in Runtime, non-deterministic collections, GC allocations).
---

# Simulation Contract Audit

This skill provides an automated static analysis scanner (`scripts/sim_audit.py`) to enforce the architectural invariants documented in `AGENTS.md` and `engine_architecture_v3.2.md`.

## Key Rules Enforced

1. **Deterministic RNG (`R01_DETERMINISTIC_RNG`)**:
   Authoritative simulation in `Runtime/` and `Contracts/` must never use `UnityEngine.Random`. Must use `Unity.Mathematics.Random` with explicit, restorable seed state.
2. **No Scene Objects in Runtime State (`R02_NO_SCENE_TRANSFORM_IN_RUNTIME`)**:
   Runtime authoritative simulation must be pure data. It must never reference `Transform`, `GameObject`, or `MonoBehaviour`.
3. **Deterministic Collections (`R03_NON_DETERMINISTIC_COLLECTION`)**:
   Standard `System.Collections.Generic.Dictionary` and `HashSet` have non-deterministic iteration order across platforms. Hot paths must use `NativeParallelHashMap` or sorted indices.
4. **Zero-Allocation Hot Paths (`R04_NO_LINQ_IN_RUNTIME`)**:
   `System.Linq` generates managed allocations in per-tick loops.
5. **Capacity Bounds Creep (`R05_CAPACITY_CREEP`)**:
   Flags any modifications to capacity bounds to prevent masking underlying memory or admission leaks.

---

## Commands & Usage

Helper script path:
`.agents/skills/sim-contract-audit/scripts/sim_audit.py`

### 1. Audit Uncommitted Changes
Inspect working tree changes before committing:

```powershell
python .agents/skills/sim-contract-audit/scripts/sim_audit.py --diff
```

### 2. Audit Candidate Commit Range (Reviewer / Coordinator)
Inspect all changes introduced between the assigned baseline and candidate SHA:

```powershell
python .agents/skills/sim-contract-audit/scripts/sim_audit.py --range f567b02027dbf31c96ee4382eb4158516c378ddd..HEAD
```

### 3. Audit Entire Directory or File
```powershell
python .agents/skills/sim-contract-audit/scripts/sim_audit.py --path Assets/Scripts/UkrainianWarfare/Runtime/Navigation/
```

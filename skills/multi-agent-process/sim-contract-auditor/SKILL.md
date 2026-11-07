---
name: sim-contract-auditor
description: Statically audit simulation and game engine code for deterministic architectural invariants: ban UnityEngine.Random in runtime (must use deterministic seeded RNG), prohibit heap allocations (new, LINQ, boxing) in hot tick loops, reject non-deterministic collection ordering, and ensure state hasher determinism.
compatibility: Platform independent. Works with C#, C++, Rust, and Python simulation codebases.
tags: [simulation, determinism, unity, csharp, memory, performance, invariants]
---

# Simulation Contract Auditor

This skill provides automated static analysis and verification patterns to preserve determinism, zero-allocation runtime performance, and snapshot-restore replay fidelity in simulation engines (such as the Trishul Tactical Engine).

## Core Determinism Invariants

### 1. No Non-Deterministic RNG in Simulation Runtime
- **BANNED**: `UnityEngine.Random`, `System.Random` without fixed seed, `Guid.NewGuid()`.
- **REQUIRED**: Deterministic, seed-injected PRNG (e.g. `Xoroshiro128Plus`, `Pcgrandom`) linked to the simulation tick index.

### 2. Zero Heap Allocation in Tick Loops
- **BANNED**:
  - `new List<T>()`, `new T[]`, or object instantiations within `OnTick()`, `FixedUpdate()`, or traversal loops.
  - LINQ queries (`.Where()`, `.Select()`, `.Any()`, `.ToList()`).
  - Boxing value types into interfaces or `object`.
  - Lambda expressions capturing local variables (creating heap closures).
- **REQUIRED**: Pre-allocated object pools, ring buffers, native arrays, or reusable scratch buffers.

### 3. Deterministic Collection Iteration
- **BANNED**: Iterating over standard hash sets or dictionaries where key order depends on hash collisions or memory addresses.
- **REQUIRED**: Sorted collections, indexed arrays, or deterministic tie-breaking (e.g. secondary sort by `EntityId`).

### 4. Engine Object Separation
- **BANNED**: Accessing `Transform`, `GameObject`, or Unity component properties from background simulation worker threads.
- **REQUIRED**: Pure data structures (ECS / DOD) in simulation kernel; presentation layer mirrors state during render frames.

## Static Audit Inspection Script (`scripts/audit_sim.py`)

```python
import re
import sys
from pathlib import Path

BANNED_PATTERNS = [
    (r"\bUnityEngine\.Random\b", "Banned UnityEngine.Random: use deterministic seeded PRNG"),
    (r"\bLINQ\b|\.Where\(|\.Select\(|\.ToList\(", "LINQ allocation in simulation code"),
    (r"\bnew\s+[A-Za-z0-9_]+\[\]", "Dynamic array allocation in tick path"),
    (r"\bGetHashCode\(\)", "Non-deterministic hash code used in logic"),
]

def audit_file(path: Path) -> list[str]:
    violations = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for idx, line in enumerate(lines, 1):
        for pattern, msg in BANNED_PATTERNS:
            if re.search(pattern, line):
                violations.append(f"{path.name}:{idx}: {msg} -> '{line.strip()}'")
    return violations
```

## Review Checklist
- [ ] No heap allocations detected in methods invoked per-tick.
- [ ] Random numbers derive solely from `SimulationContext.Rng`.
- [ ] Tie-breaking on spatial or target queries uses deterministic Entity IDs.
- [ ] State hash remains identical when reloading from a saved snapshot at tick $T$.

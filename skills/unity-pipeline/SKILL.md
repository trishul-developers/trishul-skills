---
name: unity-pipeline
description: Unified Unity C# engineering, verification, and testing pipeline. Integrates mandatory fast-fail static contract audits (<1s), fast C# compilation pre-checks, targeted batchmode test execution (EditMode/PlayMode), NUnit 3 XML report parsing, automated Editor.log failure diagnostics extraction, and composite phase gates into a single authoritative tool.
compatibility: Platform independent. Python 3 standard library only. Works with Unity 6 / 2022+ batchmode.
tags: [unity, testing, nunit, simulation, determinism, verification, logs]
---

# Unified Unity Pipeline

This skill provides an authoritative, end-to-end toolchain for Unity game and simulation engineering. It eliminates multi-turn tool wrestling by integrating static architectural contract audits, fast compilation, batchmode test execution, NUnit XML report parsing, and log inspection into a single zero-dependency script (`scripts/unity_pipeline.py`).

## Core Invariant: Mandatory Fast-Fail Pre-Check
Launching Unity in `-batchmode` takes **30 to 90 seconds**. If a developer or agent introduces a banned `UnityEngine.Random` call, captures a LINQ lambda, or introduces a compilation error, launching Unity is a complete waste of compute.

By default, `unity_pipeline.py test` executes a **1-second pre-check**:
1. **Static Invariant Audit (<0.5s)**: Scans modified files for `UnityEngine.Random`, `Transform` in Runtime state, LINQ, and dynamic array allocations.
2. **FastCompile (<1s)**: Runs `dotnet build` to verify syntax and references.
3. **If pre-check fails**: Aborts immediately with exact file and line numbers, preventing wasted engine launch cycles.
4. **If pre-check passes**: Launches Unity, executes targeted tests, and parses the resulting NUnit XML.

---

## Subcommands & Recipes

### 1. Targeted Test Run with Mandatory Pre-Check
```bash
python "skills/unity-pipeline/scripts/unity_pipeline.py" test \
  -C "E:/Projects/trishul-tactical-engine" \
  --platform EditMode \
  --filter "CombatManagerTests"
```

### 2. Fast-Fail Static Contract Audit Only (<1s)
```bash
python "skills/unity-pipeline/scripts/unity_pipeline.py" audit \
  -C "E:/Projects/trishul-tactical-engine" \
  --diff-only
```

### 3. Fast C# Compilation Check
```bash
python "skills/unity-pipeline/scripts/unity_pipeline.py" compile \
  -C "E:/Projects/trishul-tactical-engine"
```

### 4. Running a Composite Phase Gate
```bash
python "skills/unity-pipeline/scripts/unity_pipeline.py" gate \
  -C "E:/Projects/trishul-tactical-engine" \
  --phase "G02"
```

### 5. Inspecting Unity Logs on Failure
```bash
python "skills/unity-pipeline/scripts/unity_pipeline.py" logs \
  -C "E:/Projects/trishul-tactical-engine"
```

### 6. Parsing an Existing NUnit XML Report
```bash
python "skills/unity-pipeline/scripts/unity_pipeline.py" parse-xml \
  "E:/Projects/trishul-tactical-engine/test-results-editmode.xml"
```

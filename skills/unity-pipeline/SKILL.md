---
name: unity-pipeline
description: Unified Unity C# engineering, verification, and testing pipeline. Integrates machine-wide Unity execution locking, exact ProjectVersion editor resolution, mandatory fast-fail static contract audits (<1s), fast C# compilation pre-checks, targeted batchmode test execution (EditMode/PlayMode), NUnit 3 XML report parsing, automated Editor.log failure diagnostics extraction, and composite phase gates into a single authoritative tool.
compatibility: Platform independent. Python 3 standard library only. Works with Unity 6 / 2022+ batchmode.
tags: [unity, testing, nunit, simulation, determinism, verification, logs, locking]
---

# Unified Unity Pipeline

This skill provides an authoritative, end-to-end toolchain for Unity game and simulation engineering. It eliminates multi-turn tool wrestling by integrating machine-wide instance locking, exact editor version resolution, static architectural contract audits, fast compilation, batchmode test execution, NUnit XML report parsing, and log inspection into a single zero-dependency script (`scripts/unity_pipeline.py`).

## Core Invariants

### 1. One Unity at a Time (Machine-Wide Lock)
Unity locks its project Library and cache files; concurrent engine runs on the same machine corrupt state or crash. `unity_pipeline.py` enforces a machine-wide lock file under `%LOCALAPPDATA%\unity_pipeline.lock`:
- Storing PID, start time, and project path.
- **Live process check**: If held by another active process, `--lock-mode wait` (default) waits up to `--lock-timeout` (default 600s), while `--lock-mode exit` (or `--exit-if-locked`) aborts immediately with exit code 75 and a clear diagnostic message.
- **Stale lock takeover**: If the recorded PID is dead, the stale lock is taken over automatically with a notice.
- **Reliable release**: The lock is always released on normal exit, unhandled errors, and Ctrl+C (`SIGINT`/`SIGTERM`/`atexit`).

### 2. Exact Editor Resolution
The pipeline reads `m_EditorVersion` from `<projectPath>/ProjectSettings/ProjectVersion.txt` and resolves that exact editor under Unity Hub (`C:\Program Files\Unity\Hub\Editor\<version>\Editor\Unity.exe`).
- If the pinned version is not installed in Unity Hub, it fails with a clear message.
- Hardcoded fallback lists are disabled to prevent silent mismatched engine executions.
- Use `--unity-path <path>` (or env `UNITY_PATH`) for explicit path overrides.

### 3. Mandatory Fast-Fail Pre-Check
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
  -C "<repo_dir>" \
  --platform EditMode \
  --filter "CombatManagerTests" \
  --lock-mode wait
```
*Options:*
- `--lock-mode wait|exit`: Wait for lock release or exit immediately (aliases: `--wait-lock`, `--exit-if-locked`).
- `--lock-timeout <seconds>`: Max wait time in seconds (default 600).
- `--unity-path <path>`: Explicit Unity executable override.

### 2. Fast-Fail Static Contract Audit Only (<1s)
```bash
python "skills/unity-pipeline/scripts/unity_pipeline.py" audit \
  -C "<repo_dir>" \
  --diff-only
```

### 3. Fast C# Compilation Check
```bash
python "skills/unity-pipeline/scripts/unity_pipeline.py" compile \
  -C "<repo_dir>"
```

### 4. Running a Composite Phase Gate
```bash
python "skills/unity-pipeline/scripts/unity_pipeline.py" gate \
  -C "<repo_dir>" \
  --phase "G02"
```

### 5. Inspecting Unity Logs on Failure
```bash
python "skills/unity-pipeline/scripts/unity_pipeline.py" logs \
  -C "<repo_dir>"
```

### 6. Parsing an Existing NUnit XML Report
```bash
python "skills/unity-pipeline/scripts/unity_pipeline.py" parse-xml \
  "<repo_dir>/test-results-editmode.xml"
```

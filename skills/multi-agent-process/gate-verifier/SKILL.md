---
name: gate-verifier
description: Execute composite verification gates (FastCompile, EditMode tests, PlayMode tests, NUnit XML report parsing, and determinism checks) before any task handoff, PR creation, or branch merge. Use whenever validating code changes, parsing CI test output, or proving zero regressions.
compatibility: Platform independent. Works with Unity, Python (pytest), TypeScript, or .NET test runners.
tags: [testing, verification, gates, ci, quality-assurance, nunit]
---

# Standing Gate Verifier

This skill enforces strict automated gate verification before any code handoff or merge. It executes fast compilation, runs targeted test suites, parses test report XMLs, and surfaces concise, high-signal diagnostics without flooding context with raw log noise.

## Core Mandates
1. **Never Flood Chat with Raw Logs**: Extract test counts, total duration, and only the first 1–2 failing assertions with stack traces (maximum ~50 lines).
2. **Dual-Gate Verification**:
   - **Gate A (Compile & EditMode)**: Fast syntax, type checking, unit tests, and editor-mode invariants.
   - **Gate B (PlayMode & Determinism)**: Integration tests, simulation ticks, state serializability, and memory allocation invariants.
3. **Zero-Tolerance Policy**: If 1 test fails out of 500, the gate is RED. Never merge on red CI or partial passes without explicit architect waiver.

## Verification Pipeline

### Step 1: Fast Compilation
Verify that all source code compiles cleanly with zero errors before launching full test runners.
```powershell
# Fast C# compilation check
dotnet build --no-restore -c Release
```

### Step 2: Targeted Test Execution
Run EditMode or unit tests first (fastest feedback):
```powershell
# Unity batchmode EditMode test run
& "$UNITY_PATH" -batchmode -nographics -projectPath "$PROJECT_PATH" -runTests -testPlatform EditMode -testResults "test-results-editmode.xml"
```

### Step 3: XML Report Parsing
Extract structured metrics directly from the NUnit or JUnit XML artifact:
- Total tests run
- Passed count
- Failed count
- Skipped / Inconclusive count
- Execution duration
- Failure details (Class, TestName, Message, StackTrace)

### Python Parser Helper (`parse_gate.py`)
```python
import xml.etree.ElementTree as ET
import sys

def parse_nunit(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    total = root.attrib.get('total', '0')
    passed = root.attrib.get('passed', '0')
    failed = root.attrib.get('failed', '0')
    duration = root.attrib.get('duration', '0')
    
    print(f"Gate Results: {passed}/{total} passed, {failed} failed (in {duration}s)")
    if int(failed) > 0:
        for failure in root.iter('failure'):
            msg = failure.findtext('message') or ''
            stack = failure.findtext('stack-trace') or ''
            print(f"FIRST FAILURE:\n{msg}\n{stack[:500]}")
            break
```

## Standardized Gate Report Output

```markdown
### VERIFICATION GATE REPORT
- **Timestamp:** 2026-11-07 13:30 UTC
- **Target SHA:** `8d0ba39f`
- **Compiler Status:** GREEN (0 errors, 0 warnings)
- **EditMode Suite:** PASSED (142 passed, 0 failed, duration: 4.2s)
- **PlayMode Suite:** PASSED (38 passed, 0 failed, duration: 18.7s)
- **Memory Invariant:** PASSED (Zero GC allocations observed in 100-tick benchmark)
- **Gate Status:** AUTHORITATIVE GREEN (Eligible for review/merge)
```

---
name: unity-testing-workflow
description: >-
  Use this skill for running Unity tests, fast C# compilation checks, targeted test execution (EditMode/PlayMode), and parsing NUnit test report XMLs into structured handoff evidence.
---

# Unity Testing and Automation Workflow

This skill provides step-by-step procedures and a unified test automation helper (`scripts/run_unity_tests.py`) for the Ukrainian Warfare project.

## Core Rules & Policies

1. **Fast Compile Gate First**: Always verify C# syntax, interfaces, and types using `dotnet build ci/FastCompile/FastCompile.csproj` (~1.5s) before launching Unity. Catch syntax and type errors without waiting 30+ seconds for editor startup.
2. **Targeted Execution (Execution-Conservation Policy)**: Do not run all 842+ EditMode tests on every incremental iteration. Use targeted `--filter <FixtureName>` for the specific task at hand (e.g. `--filter RemediationPhase05To09Tests`, `--filter PathfindingResumptionTests`, `--filter NavHeapTests`).
3. **Truthful Evidence Reporting**: Base test counts, durations, and pass/fail lists strictly on the authoritative NUnit results XML in `Logs/`. If execution is not due or deferred, report `NOT_RUN` truthfully.

---

## Unified Test Runner Script

The helper script `.agents/skills/unity-testing-workflow/scripts/run_unity_tests.py` automates the entire compile-test-report workflow:

```powershell
# 1. Run targeted EditMode tests (automatically runs fast compile first):
python .agents/skills/unity-testing-workflow/scripts/run_unity_tests.py --mode EditMode --filter RemediationPhase05To09Tests

# 2. Run PlayMode tests:
python .agents/skills/unity-testing-workflow/scripts/run_unity_tests.py --mode PlayMode --filter PresentationPlayModeSmokeTests

# 3. Skip fast compile (if only running tests that don't affect core contracts):
python .agents/skills/unity-testing-workflow/scripts/run_unity_tests.py --mode EditMode --filter ToolchainSmokeTest --no-fast-compile

# 4. Parse an existing test results XML file without re-running:
python .agents/skills/unity-testing-workflow/scripts/run_unity_tests.py parse Logs/resumption.xml
```

The script will:
- Run `dotnet build ci/FastCompile/FastCompile.csproj` and halt immediately if compilation fails.
- Run `unity test . --mode <mode> --filter <filter> --output <xml_path> --timeout <seconds>`.
- Parse the resulting XML and display:
  - Total, Passed, Failed, and Skipped counts.
  - Duration.
  - Formatted list of passed tests.
  - Detailed error messages and stack traces for any failures.

---

## Manual Execution Reference

If executing tools individually without the runner script:

### Step 1: Fast C# Compilation Gate
```powershell
dotnet build ci/FastCompile/FastCompile.csproj --configuration Release --nologo
```

### Step 2: Run Unity Tests CLI
```powershell
unity test . --mode EditMode --filter <Pattern> --output Logs/<output_name>.xml --timeout 300
unity test . --mode PlayMode --filter <Pattern> --output Logs/<output_name>.xml --timeout 600
```

### Step 3: Parse / Inspect Results XML
Extract test outcomes from the NUnit 3 XML report using:
```powershell
python .agents/skills/unity-testing-workflow/scripts/run_unity_tests.py parse Logs/<output_name>.xml
```

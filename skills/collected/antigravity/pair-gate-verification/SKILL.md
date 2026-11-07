---
name: pair-gate-verification
description: >-
  Use this skill to run and aggregate composite Pair Gates (e.g. Pair Gate A after Phase 05+06, Pair Gate B after Phase 07+08) across FastCompile, EditMode, PlayMode, and focused suites into an authoritative gate report.
---

# Pair Gate Verification Workflow

In Ukrainian Warfare, full local project test gates are grouped after every two phase closures (rather than after every small incremental fix) to conserve execution resources while maintaining high simulation confidence.

- **Pair Gate A**: Executed on the exact accepted pair-gate SHA after Phase 05 and Phase 06 are independently source-reviewed.
- **Pair Gate B**: Executed after Phase 07 and Phase 08 are independently source-reviewed.

---

## Commands & Usage

Helper script path:
`.agents/skills/pair-gate-verification/scripts/pair_gate.py`

### 1. Run Complete Pair Gate A
Chains FastCompile, full EditMode, full PlayMode, and remediation suites, outputting `Logs/pair_gate_A_report.md`:

```powershell
python .agents/skills/pair-gate-verification/scripts/pair_gate.py --gate A
```

### 2. Run Complete Pair Gate B
```powershell
python .agents/skills/pair-gate-verification/scripts/pair_gate.py --gate B
```

### 3. Generate Report Only from Existing Logs
If tests were already executed and XML logs exist in `Logs/`:

```powershell
python .agents/skills/pair-gate-verification/scripts/pair_gate.py --gate A --report-only
```

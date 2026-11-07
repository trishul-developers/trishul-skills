---
name: snapshot-replay-verifier
description: >-
  Use this skill to execute and verify snapshot serialization, checkpoint/restore determinism, and state hasher equivalence across tick boundaries.
---

# Snapshot and Replay Verification

In Ukrainian Warfare, authoritative simulation state must be fully serializable via `WriteSnapshot -> TryReadSnapshot`, producing bit-exact hash equality and deterministic resumption.

---

## Commands & Usage

Helper script path:
`.agents/skills/snapshot-replay-verifier/scripts/verify_snapshots.py`

### 1. Run All Snapshot & Determinism Tests
Discovers and executes all tests matching `*Snapshot*|*Restore*|*Determinism*|*Resumption*`:

```powershell
python .agents/skills/snapshot-replay-verifier/scripts/verify_snapshots.py
```

### 2. Parse Existing Snapshot Results
```powershell
python .agents/skills/snapshot-replay-verifier/scripts/verify_snapshots.py --parse Logs/snapshot_verification.xml
```

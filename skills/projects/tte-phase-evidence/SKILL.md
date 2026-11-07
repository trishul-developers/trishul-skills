---
name: tte-phase-evidence
description: Assemble and verify the phase-end acceptance review package for the architect (preconditions, step commit table, CI run status, state-inventory diff, deviations) using scripts/assemble_phase_evidence.py. Use when all steps of a phase are complete. Orchestrator role.
---

# Phase-End Evidence Package (`tte-phase-evidence`)

Automates the verification and generation of the phase-end acceptance evidence block as mandated by `docs/implementation/review_protocol.md` and Plan v2 section 4.

The orchestrator cannot accept a phase; it runs this skill to verify repository preconditions, assemble the step table, extract state changes, and post the review package to the phase issue.

---

## 1. Quickstart (Single-Command Execution)

Run the automated assembler from your worktree:

```powershell
python "skills/projects/tte-phase-evidence/scripts/assemble_phase_evidence.py" `
  --phase G01 `
  --base-ref origin/main `
  --output scratch/phase_evidence.md
```

Options:
- `--phase <name>`: Required phase identifier (e.g. `G01`, `G02`, `P17`).
- `--base-ref <ref>`: Git base reference for commit range and diffs (default: `origin/main`).
- `-C <path>`: Path to repository root (defaults to `.`).
- `--branch <name>`: Branch name to query specific CI workflow runs.
- `--strict`: Fails with non-zero exit code if precondition violations exist.
- `-o, --output <path>`: Writes markdown directly to file.

---

## 2. Automated Checks & Assembly

The script automatically executes and formats:
1. **Preconditions Audit**:
   - Scans `Assets/Scripts` for forbidden markers (`HOLD(Qn)`, `NotImplementedException`, `TODO`).
   - Verifies the phase's temporary red list (`docs/implementation/plan_v2/*_temporary_red_list.md`) is empty or deleted.
2. **Step Commit Table**:
   - Parses `git log --oneline --reverse <base_ref>..HEAD` into a structured step table.
3. **CI Status Query**:
   - Queries `gh run list --workflow unity-ci.yml` for green status on both EditMode and PlayMode.
4. **State Inventory Diff**:
   - Automatically diffs `docs/implementation/state_inventory.md` against baseline and wraps in collapsible details if long.
5. **Architect Review Boundaries**:
   - Emits structured deviation notes and review boundaries.

---

## 3. Publication

Once generated, publish to GitHub using the global `github-pr-workflow` helper:
```powershell
python "skills/github-pr-workflow/scripts/gh_helper.py" comments post `
  --issue <phase-issue-number> `
  --file scratch/phase_evidence.md
```

Then notify the owner/architect in one line and **stop at the review boundary** until `ACCEPTED` is recorded.

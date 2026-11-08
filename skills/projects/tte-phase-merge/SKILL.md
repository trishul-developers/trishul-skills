---
name: tte-phase-merge
description: Safely merge side/task branches into the active TTE phase branch with a non-fast-forward merge commit (--no-ff). Enforces clean working tree, blocks unapproved ProjectSettings/Packages changes, shows merge-base and diff preview, pushes only on demand with --push, and polls for GitHub Actions CI run ID. Strictly prohibits force-pushes and touching main.
compatibility: Platform independent. Windows (PowerShell, Git Bash) and POSIX. Python 3 standard library only.
tags: [tte, git, merge, phase, orchestrator, ci]
---

# TTE Phase Merge

This skill provides an authoritative, safe merge tool for integrating side branches into the active phase branch (`g02-presentation-orders-ux`).

> [!IMPORTANT]
> **Authority Invariant**: Only the main orchestrator (`orchestrator-codex` at present, or its designated fallback orchestrator) merges code into the phase branch. Individual implementors, executors, and subagents must never merge directly to the phase branch.

## Safety & Governance Rules
1. **Never touch `main`**: Merging into or from `main` is strictly prohibited. `main` advances only upon complete whole-phase architect acceptance and owner sign-off.
2. **Never force-push**: Pushes are strictly forward-only (`git push origin <phase-branch>`).
3. **Clean tree enforcement**: Refuses execution if uncommitted changes or untracked modifications exist.
4. **Project Settings & Package Guard**: Refuses merge if diff touches `ProjectSettings/**` or `Packages/**`, unless explicitly authorized via `--allow-settings`.
5. **Pre-merge visibility**: Computes and displays the merge base and the list of modified files prior to merging.
6. **Bounded CI Run Polling**: When `--push` is specified, polls GitHub Actions until the triggered CI run ID appears, printing its direct URL.

## Usage

### 1. Dry Run / Preview Diff & Merge Base
```bash
python "skills/projects/tte-phase-merge/scripts/tte_phase_merge.py" \
  -C "E:/Projects/trishul-tactical-engine" \
  --dry-run \
  "g02-q36-stale-target"
```

### 2. Local Merge Only (No Push)
```bash
python "skills/projects/tte-phase-merge/scripts/tte_phase_merge.py" \
  -C "E:/Projects/trishul-tactical-engine" \
  "g02-q36-stale-target"
```

### 3. Merge, Push, and Poll for CI Run
```bash
python "skills/projects/tte-phase-merge/scripts/tte_phase_merge.py" \
  -C "E:/Projects/trishul-tactical-engine" \
  --push \
  "g02-q36-stale-target"
```

### Options
- `branch`: Side/task branch to merge (required).
- `--phase-branch <branch>`: Target phase branch (default: `g02-presentation-orders-ux`).
- `--allow-settings`: Bypass restriction on `ProjectSettings/**` and `Packages/**`.
- `--push`: Push merge commit to remote and poll for the created CI run ID.
- `-m`, `--message <msg>`: Custom merge commit message.
- `--dry-run`: Previews merge base and changed files without executing merge.
- `--wait-ci-timeout <sec>`: Maximum seconds to wait for CI run detection (default: 60).
- `-C`, `--dir <path>`: Path to project checkout (default: `.`).

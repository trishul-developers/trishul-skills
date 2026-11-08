---
name: tte-status
description: Authoritative TTE project status reporter. Outputs complete waking state in <=60 lines (phase branch head SHA, CI run & job conclusions, open PRs, top 8 remote branches by recency, ahead/behind main divergence, last 3 comments on phase PR and question issue cut to ~200 chars, and local worktrees). Uses only git and gh.
compatibility: Windows (PowerShell, Git Bash) and POSIX. Python 3 standard library only.
tags: [tte, status, orchestrator, manager, git, gh, ci]
---

# TTE Project Status

`tte-status` produces a single, concise snapshot (<=60 lines) of the Trishul Tactical Engine project state required by an orchestrator or manager upon waking. It eliminates dozens of exploratory tool calls across `git` and `gh`. It inspects the local git cache and GitHub via `gh`; it does not perform a `git fetch`.

## What It Reports
1. **Phase Branch & CI**: Phase head SHA, latest CI workflow run ID, conclusion, and individual job conclusions (e.g. `Fast C# compile gate`, `Unity EditMode`, `Unity PlayMode`).
2. **Phase Divergence**: Exact commit counts ahead of and behind `main`.
3. **Open PRs**: Number, branch name, title, and draft state.
4. **Remote Branches**: Top 8 remote branches sorted by most recent commit, with short SHA and relative age.
5. **Recent Context**: Last 3 comments on the phase PR (default 61) and question log issue (default 64), each cut to ~200 characters.
6. **Local Worktrees**: Worktree directories, checked-out branches, and current HEAD SHAs.

## Usage

```bash
python "skills/projects/tte-status/scripts/tte_status.py" -C "E:/Projects/trishul-tactical-engine"
```

### Options
- `--phase-branch <branch>`: Phase branch name (default: `g02-presentation-orders-ux`).
- `--pr <number>`: Phase PR number for recent comments (default: `61`).
- `--issue <number>`: Phase question log issue number for recent comments (default: `64`).
- `--repo <owner/repo>`: GitHub repo override (default: auto-detected from origin remote).
- `-C`, `--dir <path>`: Path to project checkout or worktree (default: `.`).

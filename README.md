# AI Agent Skill Hub & Custom Registry

Welcome to the central **AIAgent Skill Hub** (`E:\Projects\Skills`). This repository serves as the authoritative catalog, cross-platform bridge, and production skill library across **Anthropic Claude Code**, **OpenAI Codex**, and **Google Antigravity (AGY)**.

All generic vendor-bundled, official marketplace, and speculative skills have been removed. This repository strictly contains **21 custom skills and scripts developed by agents on this machine**, organized into flat, clean categories.

---

## 1. Quick Overview

- **Total Custom Skills Registered**: **21 skills** in [`catalog.json`](file:///E:/Projects/Skills/catalog.json)
- **Universal Headless CLI Runners**: 3 execution harnesses in [`skills/headless/`](file:///E:/Projects/Skills/skills/headless)
- **Collected Platform Custom Skills**: 11 custom skills created across Antigravity, Codex, and Claude in [`skills/collected/`](file:///E:/Projects/Skills/skills/collected)
- **Project-Specific Skills**: 7 custom skills residing in project repositories in [`skills/projects/`](file:///E:/Projects/Skills/skills/projects)

---

## 2. Repository Layout

```
E:\Projects\Skills/
  ├── catalog.json                             # Machine-readable registry of all 21 custom skills
  ├── README.md                                # Master repository documentation
  ├── scripts/
  │     ├── sync_skills.py                     # Synchronize & rebuild catalog from custom sources
  │     └── validate_skills.py                 # Lint & verify all SKILL.md and Python scripts
  ├── skills/
  │     ├── headless/                          # Universal non-interactive CLI invocation skills
  │     │     ├── codex-headless/              # Runner & SKILL.md for `codex exec`
  │     │     ├── agy-headless/                # Runner & SKILL.md for `agy -p`
  │     │     └── claude-headless/             # Runner & SKILL.md for `claude -p`
  │     ├── collected/                         # Flat list of collected platform custom skills
  │     │     ├── agy-cli/                     # Claude -> AGY runner
  │     │     ├── codex-cli/                   # Claude -> Codex runner
  │     │     ├── engineering-orchestrator/    # Canonical roles & compute governance
  │     │     ├── github-pr-comment-watcher/   # PR polling & role routing daemon
  │     │     ├── github-pr-git-workflow/      # Safe PR comments & fast-forward push
  │     │     ├── pair-gate-verification/      # Composite Pair Gates (A/B) runner
  │     │     ├── pr-handoff-lifecycle/        # Automated PR role handoffs
  │     │     ├── sim-contract-audit/          # Determinism & zero-GC invariant scanner
  │     │     ├── snapshot-replay-verifier/    # Snapshot serialization & state hasher verifier
  │     │     ├── unity-log-inspector/         # Diagnostics & compile error log scraper
  │     │     └── unity-testing-workflow/      # Batchmode testing & NUnit XML report parser
  │     └── projects/                          # Project-specific custom skills
  │           ├── cloud-role-bridge/           # Persistent cloud role bridge (ACP)
  │           ├── handoff/                     # Agent Hub handoff worker
  │           ├── tte-content-asset/           # Vehicle/infantry catalog asset ingestion (TTE)
  │           ├── tte-golden-recapture/        # Simulation replay golden re-baseliner (TTE)
  │           ├── tte-phase-evidence/          # Structured phase acceptance evidence (TTE)
  │           ├── tte-spec-step/               # Test-first spec step batch loop (TTE)
  │           └── tte-unity-test/              # Batchmode Unity test runner (TTE)
  └── docs/
        ├── SKILL_ARCHITECTURE.md              # Comparative skill architecture across platforms
        ├── HEADLESS_CLI_GUIDE.md              # Comprehensive headless CLI execution manual
        ├── MEMORY_AND_PROCESS_ANALYSIS.md     # Deep dive into project memories & rationale
        └── TAXONOMY.md                        # Master classification matrix of all 21 custom skills
```

---

## 3. Universal Headless CLI Runners

The repository includes three production-ready Python runners (`stdlib`-only) that handle Windows command-line limits, stdin streaming, process tree cleanup, and execution telemetry:

### A. OpenAI Codex (`codex-headless`)
```bash
python "skills/headless/codex-headless/scripts/codex_headless.py" \
  -m gpt-6.1-sol \
  -e high \
  -s workspace-write \
  -C "E:/Projects/trishul-tactical-engine" \
  --prompt-file "briefs/task.md"
```
*Docs*: [`skills/headless/codex-headless/SKILL.md`](file:///E:/Projects/Skills/skills/headless/codex-headless/SKILL.md)

### B. Google Antigravity (`agy-headless`)
```bash
python "skills/headless/agy-headless/scripts/agy_headless.py" \
  -m gemini-3.8-flash \
  -e medium \
  --mode auto \
  --auto-approve \
  -C "E:/Projects/trishul-tactical-engine" \
  "Inspect Unity Editor.log for compile errors."
```
*Docs*: [`skills/headless/agy-headless/SKILL.md`](file:///E:/Projects/Skills/skills/headless/agy-headless/SKILL.md)

### C. Anthropic Claude Code (`claude-headless`)
```bash
python "skills/headless/claude-headless/scripts/claude_headless.py" \
  -m claude-3-7-sonnet \
  --allowed-tools "Read,Bash(git diff)" \
  --dangerously-skip-permissions \
  -C "E:/Projects/trishul-tactical-engine" \
  "Review recent changes against architecture invariants."
```
*Docs*: [`skills/headless/claude-headless/SKILL.md`](file:///E:/Projects/Skills/skills/headless/claude-headless/SKILL.md)

---

## 4. Maintenance & Tooling

### Re-sync and Rebuild Custom Catalog
```powershell
python scripts/sync_skills.py
```

### Validate and Lint Skills
```powershell
python scripts/validate_skills.py
```

---

## 5. Documentation References
- [Skill Architecture Guide](file:///E:/Projects/Skills/docs/SKILL_ARCHITECTURE.md)
- [Headless CLI Execution Playbook](file:///E:/Projects/Skills/docs/HEADLESS_CLI_GUIDE.md)
- [Project Memories & Process Analysis](file:///E:/Projects/Skills/docs/MEMORY_AND_PROCESS_ANALYSIS.md)
- [Custom Skill Taxonomy](file:///E:/Projects/Skills/docs/TAXONOMY.md)

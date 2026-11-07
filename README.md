# AI Agent Skill Architecture & Unified Registry

Welcome to the central **AIAgent Skill Hub** (`E:\Projects\Skills`). This repository serves as the authoritative catalog, cross-platform bridge, and production skill library across **Anthropic Claude Code**, **OpenAI Codex**, and **Google Antigravity (AGY)**.

---

## 1. Quick Overview

- **Total Skills Registered**: **175 skills** in [`catalog.json`](file:///E:/Projects/Skills/catalog.json)
- **Universal Headless CLI Runners**: 3 first-class execution harnesses in [`skills/headless/`](file:///E:/Projects/Skills/skills/headless)
- **Multi-Agent Process Skills**: 6 specialized governance skills in [`skills/multi-agent-process/`](file:///E:/Projects/Skills/skills/multi-agent-process)
- **Collected Ecosystem Skills**: 166 skills synchronized across Claude, Codex, Antigravity, and active projects.

---

## 2. Repository Layout

```
E:\Projects\Skills/
  ├── catalog.json                             # Machine-readable registry of all 175 skills
  ├── scripts/
  │     ├── sync_skills.py                     # Synchronize & rebuild catalog from all platforms
  │     └── validate_skills.py                 # Lint & verify all SKILL.md and Python scripts
  ├── skills/
  │     ├── headless/                          # Universal non-interactive CLI invocation skills
  │     │     ├── codex-headless/              # Runner & SKILL.md for `codex exec`
  │     │     ├── agy-headless/                # Runner & SKILL.md for `agy -p`
  │     │     └── claude-headless/             # Runner & SKILL.md for `claude -p`
  │     ├── multi-agent-process/               # Governance skills derived from project memories
  │     │     ├── thub-messenger/              # Trishul Agent Hub messaging & polling
  │     │     ├── multi-agent-orchestrator/    # Cross-provider routing & quota governance
  │     │     ├── standing-gate-verifier/      # Dual-gate verification & NUnit XML parsing
  │     │     ├── clean-git-committer/         # Git hygiene & absolute ban on AI attribution
  │     │     ├── review-coverage-auditor/     # Explicit 3-tier review coverage accounting
  │     │     └── sim-contract-auditor/        # Static simulation determinism invariant audit
  │     └── collected/                         # Collected skills from the 3 platforms
  │           ├── antigravity/                 # 21 Antigravity skills
  │           ├── codex/                       # 84 Codex skills (system, Unity, office, cloudflare)
  │           ├── claude/                      # 55 Claude skills (LSP, web, office, meta)
  │           └── projects/                    # 6 Project skills (TTE, ACP, Agent Hub)
  └── docs/
        ├── SKILL_ARCHITECTURE.md              # Comparative skill architecture across platforms
        ├── HEADLESS_CLI_GUIDE.md              # Comprehensive headless CLI execution manual
        ├── MEMORY_AND_PROCESS_ANALYSIS.md     # Deep dive into project memories & rationale
        └── TAXONOMY.md                        # Master classification matrix of all 175 skills
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

## 4. Multi-Agent Governance & Workflow Skills

Derived from exhaustive analysis of project memories (`multi-provider-agentops`, `hub-pm-setup`, `codex-leads-from-g02-07`, and `trishul-agent-hub`):

1. **[`thub-messenger`](file:///E:/Projects/Skills/skills/multi-agent-process/thub-messenger/SKILL.md)**: Asynchronous inter-agent messaging, participant session binding, long-poll `inbox_wait`, and dead-letter supervision.
2. **[`multi-agent-orchestrator`](file:///E:/Projects/Skills/skills/multi-agent-process/multi-agent-orchestrator/SKILL.md)**: Cross-provider role decomposition (Claude Opus architect $\rightarrow$ Codex Sol implementor $\rightarrow$ Antigravity Flash executor), quota optimization, and the strict zero-self-review invariant.
3. **[`standing-gate-verifier`](file:///E:/Projects/Skills/skills/multi-agent-process/standing-gate-verifier/SKILL.md)**: Dual-gate verification (FastCompile + EditMode + PlayMode + NUnit XML report parsing), returning concise metrics ($<50$ lines) without raw log flooding.
4. **[`clean-git-committer`](file:///E:/Projects/Skills/skills/multi-agent-process/clean-git-committer/SKILL.md)**: Strict git hygiene enforcing the absolute ban on AI attribution (`Co-authored-by`), atomic commits by explicit path, commit message decision logging (`Decisions:`), and standing merge execution.
5. **[`review-coverage-auditor`](file:///E:/Projects/Skills/skills/multi-agent-process/review-coverage-auditor/SKILL.md)**: Eliminates lazy approvals by mandating explicit 3-tier categorization (`READ_IN_FULL`, `GREP_CHECKED`, `UNREAD_OUT_OF_SCOPE`).
6. **[`sim-contract-auditor`](file:///E:/Projects/Skills/skills/multi-agent-process/sim-contract-auditor/SKILL.md)**: Static analysis for simulation determinism: bans `UnityEngine.Random` in runtime, eliminates GC allocations in tick loops, and checks state hash determinism.

---

## 5. Maintenance & Tooling

### Re-sync and Rebuild Catalog
```powershell
python scripts/sync_skills.py
```

### Validate and Lint Skills
```powershell
python scripts/validate_skills.py
```

---

## 6. Documentation References
- [Skill Architecture Guide](file:///E:/Projects/Skills/docs/SKILL_ARCHITECTURE.md)
- [Headless CLI Execution Playbook](file:///E:/Projects/Skills/docs/HEADLESS_CLI_GUIDE.md)
- [Project Memories & Process Analysis](file:///E:/Projects/Skills/docs/MEMORY_AND_PROCESS_ANALYSIS.md)
- [Unified Skill Taxonomy](file:///E:/Projects/Skills/docs/TAXONOMY.md)

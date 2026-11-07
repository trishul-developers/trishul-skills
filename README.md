# AI Agent Skill Hub & Custom Registry

Welcome to the central **AIAgent Skill Hub** (`E:\Projects\Skills`). This repository serves as the authoritative catalog, cross-platform bridge, and production skill library across **Anthropic Claude Code**, **OpenAI Codex**, and **Google Antigravity (AGY)**.

All generic vendor-bundled, official marketplace, and speculative skills have been removed. This repository strictly contains **22 custom skills and scripts developed by agents on this machine**, plus the 3 universal headless CLI execution harnesses.

---

## 1. Quick Overview

- **Total Custom Skills Registered**: **22 skills** in [`catalog.json`](file:///E:/Projects/Skills/catalog.json)
- **Universal Headless CLI Runners**: 3 execution harnesses in [`skills/headless/`](file:///E:/Projects/Skills/skills/headless)
- **Collected Custom Skills**: 19 platform & project skills created by agents across Antigravity, Codex, Claude, and active repositories.

---

## 2. Repository Layout

```
E:\Projects\Skills/
  ├── catalog.json                             # Machine-readable registry of all 22 custom skills
  ├── README.md                                # Master repository documentation
  ├── scripts/
  │     ├── sync_skills.py                     # Synchronize & rebuild catalog from custom sources
  │     └── validate_skills.py                 # Lint & verify all SKILL.md and Python scripts
  ├── skills/
  │     ├── headless/                          # Universal non-interactive CLI invocation skills
  │     │     ├── codex-headless/              # Runner & SKILL.md for `codex exec`
  │     │     ├── agy-headless/                # Runner & SKILL.md for `agy -p`
  │     │     └── claude-headless/             # Runner & SKILL.md for `claude -p`
  │     └── collected/                         # Collected custom skills from this system
  │           ├── antigravity/                 # 9 Antigravity custom skills (engineering-orchestrator, sim-contract-audit, etc.)
  │           ├── codex/                       # 1 Codex custom skill (github-pr-comment-watcher)
  │           ├── claude/                      # 2 Claude custom runners (agy-cli, codex-cli)
  │           └── projects/                    # 7 Project skills (TTE, ACP, Agent Hub)
  └── docs/
        ├── SKILL_ARCHITECTURE.md              # Comparative skill architecture across platforms
        ├── HEADLESS_CLI_GUIDE.md              # Comprehensive headless CLI execution manual
        ├── MEMORY_AND_PROCESS_ANALYSIS.md     # Deep dive into project memories & rationale
        └── TAXONOMY.md                        # Master classification matrix of all 22 custom skills
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

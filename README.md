# AI Agent Skill Hub & Custom Registry

Welcome to the central **AIAgent Skill Hub** (`E:\Projects\Skills`). This repository serves as the authoritative catalog, cross-platform bridge, and production skill library across **Anthropic Claude Code**, **OpenAI Codex**, and **Google Antigravity (AGY)**.

All generic vendor-bundled, official marketplace, and duplicate speculative skills have been purged or consolidated. This repository strictly contains **14 high-leverage custom skills and script-backed harnesses** created by agents on this machine, engineered to reduce agent turns and repetitive work while maintaining high engineering quality.

---

## 1. Quick Overview

- **Total Custom Skills Registered**: **14 skills** in [`catalog.json`](file:///E:/Projects/Skills/catalog.json)
- **Universal Headless CLI Runners**: 3 execution harnesses directly in [`skills/`](file:///E:/Projects/Skills/skills)
- **Consolidated Platform Skills**: 4 skills directly in [`skills/`](file:///E:/Projects/Skills/skills)
- **Project-Specific Skills**: 7 custom skills residing in project repositories in [`skills/projects/`](file:///E:/Projects/Skills/skills/projects)

---

## 2. Repository Layout

```
E:\Projects\Skills/
  ├── catalog.json                             # Machine-readable registry of all 14 custom skills
  ├── README.md                                # Master repository documentation
  ├── scripts/
  │     ├── sync_skills.py                     # Synchronize & rebuild catalog from skills/
  │     └── validate_skills.py                 # Lint & verify SKILL.md, Python, and Node scripts
  ├── skills/
  │     ├── agy-headless/                      # Universal runner & SKILL.md for `agy -p`
  │     ├── claude-headless/                   # Universal runner & SKILL.md for `claude -p`
  │     ├── codex-headless/                    # Universal runner & SKILL.md for `codex exec`
  │     ├── engineering-orchestrator/          # Canonical roles & compute governance
  │     ├── github-pr-workflow/                # Unified PR comment watcher, safe posting & git ops
  │     ├── pr-handoff-lifecycle/              # Automated PR role handoffs & verification
  │     ├── unity-pipeline/                    # Unified compile, contract audit, test & gate pipeline
  │     └── projects/                          # Project-specific custom skills
  │           ├── chatgpt-role-bridge/         # Persistent cloud role bridge (agent-control-plane)
  │           ├── handoff/                     # Agent Hub handoff worker (trishul-agent-hub)
  │           ├── tte-content-asset/           # Vehicle/infantry catalog asset ingestion (TTE)
  │           ├── tte-golden-recapture/        # Simulation replay golden re-baseliner (TTE)
  │           ├── tte-phase-evidence/          # Structured phase acceptance evidence (TTE)
  │           ├── tte-spec-step/               # Test-first spec step batch loop (TTE)
  │           └── tte-unity-test/              # Batchmode Unity test runner (TTE)
  └── docs/
        ├── SKILL_ARCHITECTURE.md              # Comparative skill architecture across platforms
        ├── HEADLESS_CLI_GUIDE.md              # Comprehensive headless CLI execution manual
        ├── MEMORY_AND_PROCESS_ANALYSIS.md     # Deep dive into project memories & rationale
        └── TAXONOMY.md                        # Master classification matrix of all 14 custom skills
```

---

## 3. Universal Headless CLI Runners

The repository includes three production-ready Python runners (`stdlib`-only) directly in `skills/` that handle Windows command-line limits (>16k chars file-pointer fallback), stdin streaming, process tree cleanup (`taskkill /T /F`), and execution telemetry:

### A. OpenAI Codex (`codex-headless`)
```bash
python "skills/codex-headless/scripts/codex_headless.py" \
  -m gpt-6.1-sol \
  -e high \
  -s workspace-write \
  -C "E:/Projects/trishul-tactical-engine" \
  --prompt-file "briefs/task.md"
```
*Docs*: [`skills/codex-headless/SKILL.md`](file:///E:/Projects/Skills/skills/codex-headless/SKILL.md)

### B. Google Antigravity (`agy-headless`)
```bash
python "skills/agy-headless/scripts/agy_headless.py" \
  -m gemini-3.8-flash \
  -e medium \
  --mode auto \
  --auto-approve \
  -C "E:/Projects/trishul-tactical-engine" \
  "Inspect Unity Editor.log for compile errors."
```
*Docs*: [`skills/agy-headless/SKILL.md`](file:///E:/Projects/Skills/skills/agy-headless/SKILL.md)

### C. Anthropic Claude Code (`claude-headless`)
```bash
python "skills/claude-headless/scripts/claude_headless.py" \
  -m claude-3-7-sonnet \
  --allowed-tools "Read,Bash(git diff)" \
  --dangerously-skip-permissions \
  -C "E:/Projects/trishul-tactical-engine" \
  "Review recent changes against architecture invariants."
```
*Docs*: [`skills/claude-headless/SKILL.md`](file:///E:/Projects/Skills/skills/claude-headless/SKILL.md)

---

## 4. Consolidated Platform Skills

### A. Unified Unity Pipeline (`unity-pipeline`)
Consolidates fast compile checks, determinism audits, batchmode testing, NUnit XML parsing, failure log extraction, and composite Pair Gates into a single tool:
```powershell
# Mandatory <1s pre-check (aborts before launching Unity if invariant violations exist)
python skills/unity-pipeline/scripts/unity_pipeline.py all --pre-check --suite FastCompile,EditMode
```
*Docs*: [`skills/unity-pipeline/SKILL.md`](file:///E:/Projects/Skills/skills/unity-pipeline/SKILL.md)

### B. Unified GitHub PR Workflow (`github-pr-workflow`)
Combines zero-dependency pure-Python GitHub REST API interactions, state-tracking watcher daemons, and git verification:
```powershell
python skills/github-pr-workflow/scripts/gh_helper.py comments post --pr 28 --file scratch/handoff.md
```
*Docs*: [`skills/github-pr-workflow/SKILL.md`](file:///E:/Projects/Skills/skills/github-pr-workflow/SKILL.md)

### C. ChatGPT Role Bridge (`chatgpt-role-bridge`)
Portable session bridge with dynamic ACP loader enabling seamless communication with persistent cloud ChatGPT roles:
```powershell
node skills/projects/chatgpt-role-bridge/scripts/bridge.mjs status
```
*Docs*: [`skills/projects/chatgpt-role-bridge/SKILL.md`](file:///E:/Projects/Skills/skills/projects/chatgpt-role-bridge/SKILL.md)

---

## 5. Maintenance & Tooling

### Re-sync and Rebuild Custom Catalog
```powershell
python scripts/sync_skills.py
```

### Validate, Lint, and Test All Skills
```powershell
python scripts/validate_skills.py
```

### Deploy Skills Globally across Providers (Claude, Codex, Antigravity, OpenCode)
```powershell
python scripts/deploy_global_skills.py
```

---

## 6. Documentation References
- [Skill Architecture Guide](file:///E:/Projects/Skills/docs/SKILL_ARCHITECTURE.md)
- [Headless CLI Execution Playbook](file:///E:/Projects/Skills/docs/HEADLESS_CLI_GUIDE.md)
- [Project Memories & Process Analysis](file:///E:/Projects/Skills/docs/MEMORY_AND_PROCESS_ANALYSIS.md)
- [Custom Skill Taxonomy](file:///E:/Projects/Skills/docs/TAXONOMY.md)

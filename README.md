# AI Agent Skill Hub & Custom Registry

Welcome to the central **AIAgent Skill Hub** (`trishul-skills`). This repository serves as the authoritative catalog, cross-platform bridge, and production skill library across **Anthropic Claude Code**, **OpenAI Codex**, **Google Antigravity (AGY)**, and **OpenCode**.

All generic vendor-bundled, official marketplace, and duplicate speculative skills have been purged or consolidated. This repository strictly contains **17 high-leverage custom skills and script-backed harnesses** created by agents on this machine, engineered to reduce agent turns and repetitive work while maintaining high engineering quality.

---

## 1. Quick Overview

- **Total Custom Skills Registered**: **17 skills** in [`catalog.json`](./catalog.json)
- **Universal Headless CLI Runners**: 3 execution harnesses directly in [`skills/`](./skills)
- **Consolidated Platform Skills**: 5 skills directly in [`skills/`](./skills)
- **Project-Specific Skills**: 9 custom skills residing in project repositories in [`skills/projects/`](./skills/projects)

---

## 2. Repository Layout

```
trishul-skills/
  ├── catalog.json                             # Machine-readable registry of all 17 custom skills
  ├── README.md                                # Master repository documentation
  ├── scripts/
  │     ├── sync_skills.py                     # Synchronize & rebuild catalog from skills/
  │     ├── validate_skills.py                 # Lint & verify SKILL.md, Python, and Node scripts
  │     └── deploy_global_skills.py            # Global synchronization across all providers
  ├── skills/
  │     ├── agy-headless/                      # Universal runner & SKILL.md for `agy -p`
  │     ├── claude-headless/                   # Universal runner & SKILL.md for `claude -p`
  │     ├── codex-headless/                    # Universal runner & SKILL.md for `codex exec`
  │     ├── engineering-orchestrator/          # Canonical roles & compute governance
  │     ├── github-pr-workflow/                # Unified PR comment watcher, safe posting, CI digest & git ops
  │     ├── hub-messenger/                     # Zero-model Agent Hub poller & wakeup daemon
  │     ├── pr-handoff-lifecycle/              # Automated PR role handoffs & verification
  │     ├── unity-pipeline/                    # Unified lock, compile, contract audit, test & gate pipeline
  │     └── projects/                          # Project-specific custom skills
  │           ├── chatgpt-role-bridge/         # Persistent cloud role bridge (agent-control-plane)
  │           ├── handoff/                     # Agent Hub handoff worker (trishul-agent-hub)
  │           ├── tte-batch-brief/             # Standard manager-to-orchestrator batch brief template (TTE)
  │           ├── tte-batch-review/            # Lean batch-review procedure and blocker rules (TTE)
  │           ├── tte-content-pipeline/        # Register validation, key hashing & asset baking (TTE)
  │           ├── tte-golden-recapture/        # Simulation replay golden re-baseliner (TTE)
  │           ├── tte-phase-evidence/          # Automated phase acceptance evidence block generator (TTE)
  │           ├── tte-phase-merge/             # Safe --no-ff phase branch merge with CI run detection (TTE)
  │           └── tte-status/                  # Wake-up project status snapshot in <=60 lines (TTE)
  └── docs/
        ├── SKILL_ARCHITECTURE.md              # Comparative skill architecture across platforms
        ├── HEADLESS_CLI_GUIDE.md              # Comprehensive headless CLI execution manual
        ├── MEMORY_AND_PROCESS_ANALYSIS.md     # Deep dive into project memories & rationale
        └── TAXONOMY.md                        # Master classification matrix of all 12 custom skills
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
*Docs*: [`skills/codex-headless/SKILL.md`](./skills/codex-headless/SKILL.md)

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
*Docs*: [`skills/agy-headless/SKILL.md`](./skills/agy-headless/SKILL.md)

### C. Anthropic Claude Code (`claude-headless`)
```bash
python "skills/claude-headless/scripts/claude_headless.py" \
  -m claude-3-7-sonnet \
  --allowed-tools "Read,Bash(git diff)" \
  --dangerously-skip-permissions \
  -C "E:/Projects/trishul-tactical-engine" \
  "Review recent changes against architecture invariants."
```
*Docs*: [`skills/claude-headless/SKILL.md`](./skills/claude-headless/SKILL.md)

---

## 4. Consolidated High-Leverage Skills

### A. Unified Unity Pipeline (`unity-pipeline`)
Consolidates fast compile checks, determinism audits, batchmode testing, NUnit XML parsing, failure log extraction, and composite Pair Gates into a single tool:
```powershell
# Mandatory <1s pre-check (aborts before launching Unity if invariant violations exist)
python skills/unity-pipeline/scripts/unity_pipeline.py all --pre-check --suite FastCompile,EditMode
```
*Docs*: [`skills/unity-pipeline/SKILL.md`](./skills/unity-pipeline/SKILL.md)

### B. Unified GitHub PR Workflow (`github-pr-workflow`)
Combines zero-dependency pure-Python GitHub REST API interactions, state-tracking watcher daemons, and git verification:
```powershell
python skills/github-pr-workflow/scripts/gh_helper.py comments post --pr 28 --file scratch/handoff.md
```
*Docs*: [`skills/github-pr-workflow/SKILL.md`](./skills/github-pr-workflow/SKILL.md)

### C. Automated TTE Phase Evidence (`tte-phase-evidence`)
Audits repository preconditions (`HOLD(Qn)`, red list, CI head status) and automatically generates the complete 9-part acceptance evidence package:
```powershell
python skills/projects/tte-phase-evidence/scripts/assemble_phase_evidence.py --phase G01 --output scratch/evidence.md
```
*Docs*: [`skills/projects/tte-phase-evidence/SKILL.md`](./skills/projects/tte-phase-evidence/SKILL.md)

### D. TTE Content Pipeline & Register Validator (`tte-content-pipeline`)
Fast offline validation of register JSON, unit vocabulary, and 32-bit FNV-1a `DefinitionId` collision checks:
```powershell
python skills/projects/tte-content-pipeline/scripts/validate_content_asset.py --key plc.mbt.a
```
*Docs*: [`skills/projects/tte-content-pipeline/SKILL.md`](./skills/projects/tte-content-pipeline/SKILL.md)

### E. TTE Project Wakeup Status (`tte-status`)
One command that prints the full project status required on waking in <= 60 lines:
```powershell
python skills/projects/tte-status/scripts/tte_status.py -C "E:/Projects/trishul-tactical-engine"
```
*Docs*: [`skills/projects/tte-status/SKILL.md`](./skills/projects/tte-status/SKILL.md)

### F. Safe TTE Phase Branch Merge (`tte-phase-merge`)
Merges side branch into phase branch (`--no-ff`), enforces clean tree, protects project settings, and polls CI run:
```powershell
python skills/projects/tte-phase-merge/scripts/tte_phase_merge.py -C "E:/Projects/trishul-tactical-engine" --push "g02-q36-stale-target"
```
*Docs*: [`skills/projects/tte-phase-merge/SKILL.md`](./skills/projects/tte-phase-merge/SKILL.md)

### G. Trishul Agent Hub Messenger Daemon (`hub-messenger`)
Zero-model poller and waking harness for Agent Hub participants with unread inbox messages:
```powershell
python skills/hub-messenger/scripts/hub_messenger.py --token-file "C:\Users\tosum\TrishulAgentHub\tokens\owner.token" --target log
```
*Docs*: [`skills/hub-messenger/SKILL.md`](./skills/hub-messenger/SKILL.md)

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
- [Skill Architecture Guide](./docs/SKILL_ARCHITECTURE.md)
- [Headless CLI Execution Playbook](./docs/HEADLESS_CLI_GUIDE.md)
- [Project Memories & Process Analysis](./docs/MEMORY_AND_PROCESS_ANALYSIS.md)
- [Custom Skill Taxonomy](./docs/TAXONOMY.md)

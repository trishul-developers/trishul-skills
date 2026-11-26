# AI Agent Skill Hub & Custom Registry

Welcome to the central **AIAgent Skill Hub** (`trishul-skills`). This repository serves as the authoritative catalog, cross-platform bridge, and production skill library across **Anthropic Claude Code**, **OpenAI Codex**, **Google Antigravity (AGY)**, and **OpenCode**.

All generic vendor-bundled, official marketplace, and duplicate speculative skills have been purged or consolidated. This repository currently maintains **15 active custom skills and script-backed harnesses** (plus **9 retired skills** preserved under `skills/archive/`), engineered to reduce agent turns and repetitive work while maintaining high engineering quality.

---

## 1. Quick Overview

- **Total Active Skills Registered**: **15 skills** in [`catalog.json`](./catalog.json)
- **Universal Headless CLI Runners**: 4 execution harnesses directly in [`skills/`](./skills) (`agy-headless`, `agy-wsl-headless`, `claude-headless`, `codex-headless`)
- **Consolidated Platform Skills**: 5 skills directly in [`skills/`](./skills) (`agent-delivery`, `agy-quota`, `codex-quota`, `github-pr-workflow`, `unity-pipeline`)
- **Project-Specific Skills**: 6 custom skills in [`skills/projects/`](./skills/projects) (`chatgpt-role-bridge`, `ingest-staging-zips`, `tte-asset-pipeline`, `tte-content-pipeline`, `tte-golden-recapture`, `tte-phase-evidence`)
- **Archived Skills**: 9 retired hub/legacy skills in `skills/archive/` (excluded from `catalog.json` and `validate_skills.py`)

---

## 2. Repository Layout

```
trishul-skills/
  ├── catalog.json                             # Machine-readable registry of all 15 active skills
  ├── README.md                                # Master repository documentation
  ├── scripts/
  │     ├── sync_skills.py                     # Synchronize & rebuild catalog from skills/
  │     ├── validate_skills.py                 # Lint & verify SKILL.md, Python/JS scripts, model consistency & tests
  │     ├── deploy_global_skills.py            # On-demand project-local or global deployment CLI
  │     └── tests/
  │           └── test_deploy_global_skills.py # Unit tests for deployment & cross-agent rules
  ├── skills/
  │     ├── agent-delivery/                    # One-driver multi-model delivery workflow, brief templates & runlog
  │     ├── agy-headless/                      # Universal runner & SKILL.md for `agy -p`
  │     ├── agy-quota/                         # Antigravity quota, credits & model availability checker
  │     ├── agy-wsl-headless/                  # WSL runner & SKILL.md for `agy -p` with native `swarm` support
  │     ├── claude-headless/                   # Universal runner & SKILL.md for `claude -p`
  │     ├── codex-headless/                    # Universal runner & SKILL.md for `codex exec`
  │     ├── codex-quota/                       # Non-interactive Codex rate limit & quota checker (`codex app-server`)
  │     ├── github-pr-workflow/                # Unified PR comment watcher, safe posting, CI digest, ci wait & git ops
  │     ├── unity-pipeline/                    # Unified lock, compile, contract audit, test & gate pipeline
  │     ├── projects/                          # Project-specific custom skills
  │     │     ├── chatgpt-role-bridge/         # Persistent cloud role bridge (agent-control-plane)
  │     │     ├── ingest-staging-zips/         # Staging zip intake, split & SHA-256 verification (tte-art-staging)
  │     │     ├── tte-asset-pipeline/          # External art asset requirements, delivery check & Unity import (TTE)
  │     │     ├── tte-content-pipeline/        # Register validation, key hashing & asset baking (TTE)
  │     │     ├── tte-golden-recapture/        # Simulation replay golden re-baseliner (TTE)
  │     │     └── tte-phase-evidence/          # Automated phase acceptance evidence block generator (TTE)
  │     └── archive/                           # Retired hub & legacy skills (not indexed or deployed)
  └── docs/
        ├── SKILL_ARCHITECTURE.md              # Comparative skill architecture across platforms
        ├── HEADLESS_CLI_GUIDE.md              # Comprehensive headless CLI execution manual
        ├── MEMORY_AND_PROCESS_ANALYSIS.md     # Deep dive into project memories & rationale
        └── TAXONOMY.md                        # Master classification matrix
```

---

## 3. Universal Headless CLI Runners

The repository includes three production-ready Python runners (`stdlib`-only) directly in `skills/` that handle Windows command-line limits (>16k chars file-pointer fallback), stdin streaming, process tree cleanup (`taskkill /T /F`), and execution telemetry.

> **Cross-agent rule:** Headless runners are deployed *across* agents, never on the same agent (`claude` gets `agy-headless` + `codex-headless`; `codex` gets `agy-headless` + `claude-headless`; `antigravity` gets `claude-headless` + `codex-headless`).

### A. OpenAI Codex (`codex-headless`)
```bash
python "skills/codex-headless/scripts/codex_headless.py" \
  -m gpt-6.2-sol \
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

### A. One-Driver Multi-Model Delivery (`agent-delivery`)
Plans, briefs, dispatches (native subagents or headless runners), enforces cross-provider reviews, and records events in `.local/delivery/runlog.jsonl`:
```powershell
python skills/agent-delivery/scripts/delivery.py -C "E:/Projects/trishul-tactical-engine" roles
python skills/agent-delivery/scripts/delivery.py -C "E:/Projects/trishul-tactical-engine" status
```
*Docs*: [`skills/agent-delivery/SKILL.md`](./skills/agent-delivery/SKILL.md)

### B. Unified Unity Pipeline (`unity-pipeline`)
Consolidates fast compile checks, determinism audits, batchmode testing, NUnit XML parsing, failure log extraction, and composite Pair Gates into a single tool:
```powershell
# Mandatory <1s pre-check (aborts before launching Unity if invariant violations exist)
python skills/unity-pipeline/scripts/unity_pipeline.py test --platform EditMode
```
*Docs*: [`skills/unity-pipeline/SKILL.md`](./skills/unity-pipeline/SKILL.md)

### C. Unified GitHub PR Workflow (`github-pr-workflow`)
Combines zero-dependency pure-Python GitHub REST API interactions, state-tracking watcher daemons, compact CI failure digests, quiet CI run waiting, and git verification:
```powershell
# Safe PR comment posting:
python skills/github-pr-workflow/scripts/gh_helper.py comments post --pr 28 --file scratch/handoff.md

# Quiet CI wait with wake-up report:
python skills/github-pr-workflow/scripts/gh_helper.py ci wait --repo tosumitdhaka/trishul-tactical-engine --sha <sha>
```
*Docs*: [`skills/github-pr-workflow/SKILL.md`](./skills/github-pr-workflow/SKILL.md)

### D. Automated TTE Phase Evidence (`tte-phase-evidence`)
Audits repository preconditions (`HOLD(Qn)`, red list, CI head status) and automatically generates the complete 9-part acceptance evidence package:
```powershell
python skills/projects/tte-phase-evidence/scripts/assemble_phase_evidence.py --phase G01 --output scratch/evidence.md
```
*Docs*: [`skills/projects/tte-phase-evidence/SKILL.md`](./skills/projects/tte-phase-evidence/SKILL.md)

### E. TTE Content Pipeline & Register Validator (`tte-content-pipeline`)
Fast offline validation of register JSON, unit vocabulary, and 32-bit FNV-1a `DefinitionId` collision checks:
```powershell
python skills/projects/tte-content-pipeline/scripts/validate_content_asset.py --key plc.mbt.a
```
*Docs*: [`skills/projects/tte-content-pipeline/SKILL.md`](./skills/projects/tte-content-pipeline/SKILL.md)

---

## 5. Maintenance & On-Demand Deployment

> **Deployment policy:** Skills are **never deployed automatically** when created or edited. Install skills only on explicit user request, either project-locally or globally.

### Re-sync and Rebuild Custom Catalog
```powershell
python scripts/sync_skills.py
```

### Validate, Lint, and Test All Skills
```powershell
python scripts/validate_skills.py
python -m unittest scripts/tests/test_deploy_global_skills.py
```

### Deploy Skills On Demand (Project-Local or Global)
```powershell
# List active skills and per-agent cross-agent defaults
python scripts/deploy_global_skills.py --list

# Install specific skills into a project for Claude (.claude/skills)
python scripts/deploy_global_skills.py --project E:\Projects\MyProj --agent claude --skill unity-pipeline --skill github-pr-workflow

# Install into a project's shared .agents/skills (Codex & Antigravity)
python scripts/deploy_global_skills.py --project E:\Projects\MyProj --agent agents --skill unity-pipeline --skill github-pr-workflow

# Preview or run a global install for a specific agent (cross-agent headless rules enforced)
python scripts/deploy_global_skills.py --scope global --agent codex --dry-run
```

---

## 6. Documentation References
- [Skill Architecture Guide](./docs/SKILL_ARCHITECTURE.md)
- [Headless CLI Execution Playbook](./docs/HEADLESS_CLI_GUIDE.md)
- [Project Memories & Process Analysis](./docs/MEMORY_AND_PROCESS_ANALYSIS.md)
- [Custom Skill Taxonomy](./docs/TAXONOMY.md)

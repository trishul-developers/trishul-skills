# Custom Agent Skills Registry & Taxonomy

This document catalogs and classifies the **26 custom skills and scripts** created by agents on this machine across Claude, Codex, Antigravity, and active projects (`trishul-tactical-engine`, `trishul-agent-hub`, `agent-control-plane`). All public, vendor-bundled, and marketplace skills have been filtered out.

---

## 1. High-Level Summary by Platform

```mermaid
pie title Custom Skills Distribution by Source Platform
    "Antigravity Custom (9)" : 9
    "Project-Specific (7)" : 7
    "Multi-Agent Process (4)" : 4
    "Headless Runners (3)" : 3
    "Claude Custom CLI (2)" : 2
    "Codex Custom Watcher (1)" : 1
```

---

## 2. Categorized Skill Inventory

### A. Universal Headless CLI Runners (`skills/headless/`)
*Custom Python runners with process tree supervision, telemetry, and Windows command-line limit handling.*
1. **[`codex-headless`](file:///E:/Projects/Skills/skills/headless/codex-headless/SKILL.md)**: Universal runner for `codex exec` (model selection, effort, sandboxing, schemas, worktrees, thread resumption).
2. **[`agy-headless`](file:///E:/Projects/Skills/skills/headless/agy-headless/SKILL.md)**: Universal runner for `agy -p` (model selection, effort, modes, output formatting, transparent file pointers for long briefs).
3. **[`claude-headless`](file:///E:/Projects/Skills/skills/headless/claude-headless/SKILL.md)**: Universal runner for `claude -p` (model tiers, allowed tools, system prompts, decoupled stdin, bare execution).

---

### B. Multi-Agent Governance & Workflow Process (`skills/multi-agent-process/`)
*Operational workflow skills derived from project memories and multi-agent coordination requirements.*
1. **[`thub-messenger`](file:///E:/Projects/Skills/skills/multi-agent-process/thub-messenger/SKILL.md)**: Inter-agent messaging, participant session binding, long-poll `inbox_wait`, and headless participant dispatch via Trishul Agent Hub (`thub`).
2. **[`gate-verifier`](file:///E:/Projects/Skills/skills/multi-agent-process/gate-verifier/SKILL.md)**: Composite dual-gate verification pipeline (FastCompile + EditMode + PlayMode + NUnit XML report parsing), returning concise metrics ($<50$ lines).
3. **[`git-committer`](file:///E:/Projects/Skills/skills/multi-agent-process/git-committer/SKILL.md)**: Disciplined Git workflow enforcing zero AI attribution, atomic commits by explicit path, commit decision logging (`Decisions:`), and standing merge execution on green gates.
4. **[`coverage-auditor`](file:///E:/Projects/Skills/skills/multi-agent-process/coverage-auditor/SKILL.md)**: PR and code review auditor enforcing explicit 3-tier coverage classification (`READ_IN_FULL`, `GREP_CHECKED`, `UNREAD_OUT_OF_SCOPE`) and banning speculative soundness claims on unread code.

---

### C. Antigravity Custom Skills (`skills/collected/antigravity/`)
*Custom skills and scripts developed on this machine under `C:\Users\tosum\.gemini\config\skills`.*
1. **[`engineering-orchestrator`](file:///E:/Projects/Skills/skills/collected/antigravity/engineering-orchestrator/SKILL.md)**: Multi-agent orchestration, canonical roles (Architect, Implementor, Reviewer, Executor), subagent lifecycle, compute governance.
2. **[`github-pr-git-workflow`](file:///E:/Projects/Skills/skills/collected/antigravity/github-pr-git-workflow/SKILL.md)**: Safe PR comments via `scripts/gh_helper.py`, git clean status, exact SHA matching, fast-forward pushing.
3. **[`handoff`](file:///E:/Projects/Skills/skills/collected/antigravity/handoff/SKILL.md)**: Checking and acting on file-based handoffs in trishul-agent-hub.
4. **[`pair-gate-verification`](file:///E:/Projects/Skills/skills/collected/antigravity/pair-gate-verification/SKILL.md)**: Running and aggregating composite Pair Gates (A/B) via `scripts/pair_gate.py`.
5. **[`pr-handoff-lifecycle`](file:///E:/Projects/Skills/skills/collected/antigravity/pr-handoff-lifecycle/SKILL.md)**: Drafting and verifying PR role handoffs from git history, diffs, and NUnit reports via `scripts/handoff.py`.
6. **[`sim-contract-audit`](file:///E:/Projects/Skills/skills/collected/antigravity/sim-contract-audit/SKILL.md)**: Static analysis scanner `scripts/sim_audit.py` checking for `UnityEngine.Random`, `Transform` in Runtime, LINQ, and GC allocations.
7. **[`snapshot-replay-verifier`](file:///E:/Projects/Skills/skills/collected/antigravity/snapshot-replay-verifier/SKILL.md)**: Verifying snapshot serialization and state hasher equivalence via `scripts/verify_snapshots.py`.
8. **[`unity-log-inspector`](file:///E:/Projects/Skills/skills/collected/antigravity/unity-log-inspector/SKILL.md)**: Inspecting and filtering Unity Editor logs (`Editor.log`, `upm.log`) via `scripts/inspect_unity_logs.py`.
9. **[`unity-testing-workflow`](file:///E:/Projects/Skills/skills/collected/antigravity/unity-testing-workflow/SKILL.md)**: Running Unity tests and parsing NUnit report XMLs via `scripts/run_unity_tests.py`.

---

### D. Codex Custom Skills (`skills/collected/codex/`)
*Custom skill and scripts created on this machine under `C:\Users\tosum\.codex\skills`.*
1. **[`github-pr-comment-watcher`](file:///E:/Projects/Skills/skills/collected/codex/github-pr-comment-watcher/SKILL.md)**: PR comment polling, role routing, and watcher daemon (`scripts/gh_watch.py`, `scripts/pr_handoff_router_poll.py`).

---

### E. Claude Custom Skills (`skills/collected/claude/`)
*Custom runner scripts created on this machine under `C:\Users\tosum\.claude\skills`.*
1. **[`agy-cli`](file:///E:/Projects/Skills/skills/collected/claude/agy-cli/SKILL.md)**: Antigravity task runner (`scripts/agy_task.py`) for delegating tasks from Claude to `agy`.
2. **[`codex-cli`](file:///E:/Projects/Skills/skills/collected/claude/codex-cli/SKILL.md)**: Codex task runner (`scripts/codex_task.py`) for delegating tasks from Claude to `codex exec`.

---

### F. Project-Specific Skills (`skills/collected/projects/`)
*Custom skills residing inside repository trees.*
1. **[`tte-content-asset`](file:///E:/Projects/Skills/skills/collected/projects/tte-content-asset/SKILL.md)**: Content catalog and vehicle/infantry asset ingestion for TTE.
2. **[`tte-golden-recapture`](file:///E:/Projects/Skills/skills/collected/projects/tte-golden-recapture/SKILL.md)**: Re-baselining and validating golden simulation replay recordings for TTE.
3. **[`tte-phase-evidence`](file:///E:/Projects/Skills/skills/collected/projects/tte-phase-evidence/SKILL.md)**: Generating structured phase acceptance evidence blocks for TTE.
4. **[`tte-spec-step`](file:///E:/Projects/Skills/skills/collected/projects/tte-spec-step/SKILL.md)**: Test-first phase spec step implementation loop for TTE.
5. **[`tte-unity-test`](file:///E:/Projects/Skills/skills/collected/projects/tte-unity-test/SKILL.md)**: High-speed batchmode Unity test execution for TTE.
6. **[`cloud-role-bridge`](file:///E:/Projects/Skills/skills/collected/projects/cloud-role-bridge/SKILL.md)**: Persistent cloud ChatGPT session bridge (`scripts/bridge.mjs`, `bridge-lib.mjs`) for agent-control-plane.
7. **[`handoff`](file:///E:/Projects/Skills/skills/collected/projects/handoff/SKILL.md)**: File-based handoff worker for trishul-agent-hub.

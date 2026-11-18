---
name: engineering-orchestrator
description: >-
  Use this skill whenever orchestrating software engineering projects, managing multi-agent workflows,
  defining canonical roles (Architect, Implementor, Reviewer, Executor), inventing novel specialized roles on demand,
  enforcing dual-gate review/execution verification, or governing subagent lifecycle and compute costs.
---

# Autonomous Engineering Orchestrator Skill

This skill provides the authoritative runbook, prompt templates, and lifecycle procedures for Antigravity main agents acting as **Engineering Orchestrators / Coordinators**.

---

## 1. Operating Model & Separation of Concerns

The Orchestrator maintains top-down authority over the project state machine, linear milestones, and quality gates, while delegating all tactical execution to bounded subagents.

```
                    ┌───────────────────────────────────┐
                    │      COORDINATOR / ORCHESTRATOR    │
                    │   (Main Agent: State, Gates, SHAs)│
                    └─────────────────┬─────────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         ▼                            ▼                            ▼
┌───────────────────┐        ┌───────────────────┐        ┌───────────────────┐
│    IMPLEMENTOR    │        │     REVIEWER      │        │     EXECUTOR      │
│  (Bounded Paths,  │◄──────►│ (Independent Audit│        │ (Target Env, Pins,│
│   Source Author)  │remutate│   Read-Only Diff) │        │  Tests & Teardown)│
└───────────────────┘        └───────────────────┘        └───────────────────┘
         ▲                            ▲                            ▲
         └────────────────────────────┼────────────────────────────┘
                                      │ (Dynamic Canonical Roles)
                         ┌────────────┴────────────┐
                         ▼                         ▼
               ┌───────────────────┐     ┌───────────────────┐
               │     ARCHITECT     │     │ SECURITY AUDITOR  │
               │ (Contracts, ADRs) │     │ (Threats, Crypto) │
               └───────────────────┘     └───────────────────┘
                         ▼                         ▼
               ┌───────────────────┐     ┌───────────────────┐
               │    BENCHMARKER    │     │  CUSTOM NOVEL     │
               │ (Latency, Memory) │     │  ROLES (Genesis)  │
               └───────────────────┘     └───────────────────┘
```

---

## 2. Defining Canonical Roles & The Role Genesis Protocol

### A. Core Execution Roles

| Role Name | Authority Scope | Typical Tool Groups | Success Deliverable |
| :--- | :--- | :--- | :--- |
| **COORDINATOR** | Global state, gates, user communication | All tools (Coordinator mode) | `ORCHESTRATOR_RESULT v1` |
| **IMPLEMENTOR** | Code changes strictly within Allowed Paths | Read, write, test commands | Candidate SHA + local test report |
| **REVIEWER** | Read-only inspection of diffs and specs | Read-only tools | `CLOUD_ROLE_RESULT v1 (SOURCE_REVIEW)` |
| **EXECUTOR** | Clean environment build, full test suite | Terminal execution, SSH, cloud | `CLOUD_ROLE_RESULT v1 (EXECUTOR)` |
| **ARCHITECT** | System design proposals, ADRs, schemas | Read, documentation writing | Approved ADR/DCR proposal doc |
| **SECURITY_AUDITOR**| Static audit for auth/fencing/injection | Read-only tools, AST grep | Security audit matrix & risk review |
| **BENCHMARKER** | Latency, throughput, RSS benchmarking | Execution & profiling tools | Quantitative benchmark report |

### B. The Role Genesis Protocol (Inventing Novel Roles on Demand)
The Orchestrator is **explicitly authorized to invent and spawn novel specialized roles** whenever a project task diverges from standard roles. Examples include:
* `ChaosInjector` (injecting network partitions, simulated clock skew, disk full faults).
* `FuzzTester` (generating randomized corpus inputs to probe parser invariants).
* `A11yAuditor` (verifying WCAG accessibility compliance across frontend components).
* `LicenseAuditor` (inspecting transitive dependency licenses for copyleft/GPL contamination).
* `HardwareTester` (interfacing with physical devices, serial ports, or hardware-in-the-loop).

### C. The 4 Mandatory Guardrails for Novel Roles
Whenever the Orchestrator creates a new role, the role MUST strictly adhere to:
1. **Single Responsibility**: The role must have a single, crisp, domain-specific mission. Never create ambiguous generalist roles (e.g. `FullStackHelper` or `ProblemSolver`).
2. **Declared Authority Class**: The Orchestrator must explicitly declare whether the role is:
   - **Authoring Tier**: Allowed to write/mutate specific allowed paths.
   - **Audit / Execution Tier**: Strictly read-only or diagnostic; zero source mutation authority.
3. **Anti-Smear Invariant (No Self-Approval)**: If a custom role authors code, schemas, or designs, it can **never** review or approve its own deliverables. An independent Reviewer or Auditor role must still perform the quality gate.
4. **Standard Bounded Envelope**: The custom role must receive the standard dispatch contract (Request ID, Start SHA/Baseline, Allowed Paths, and Stop Conditions).

---

## 3. Standard Subagent Dispatch Templates

### Template A: Implementor Dispatch
```markdown
You are the IMPLEMENTOR subagent for Milestone <milestone_name>.

### Mission Context & Boundaries
- Repository: <repo_name>
- Branch: <branch_name>
- Start SHA: <start_sha>
- Request ID: <request_id>
- Purpose: <purpose>
- Governing Contract: <design_or_adr_doc>

### Allowed Paths
- <path_1>
- <path_2>

### Forbidden Paths
- <forbidden_path_1>
- All other paths outside the allowed list.

### Implementation Tasks
1. <objective_1>
2. Run targeted local tests: <test_command>
3. Verify linter & formatting: <lint_command>
4. Stage and commit only allowed paths: git add <allowed_path_1> <allowed_path_2> && git commit -m "<commit_message>". (MANDATORY: Never use wildcard staging such as git commit -am or git add -A, especially in Unity or mixed workspaces).
5. Push candidate commit to origin/<branch>.
6. Return structured IMPLEMENTOR report with candidate SHA, file diffs, and test results.
```

### Template B: Independent Reviewer Dispatch
```markdown
You are the INDEPENDENT READ-ONLY REVIEWER subagent for Milestone <milestone_name>.

### Mission Context & Boundaries
- Candidate SHA: <candidate_sha>
- Base SHA: <base_sha>
- Request ID: <request_id>
- Governing Contract: <contract_reference>

### Review Objectives & Standards
1. Conduct an independent read-only audit of git diff <base_sha>..<candidate_sha>.
2. Scope & Mutation Compliance: Verify only allowed paths were modified and zero forbidden paths were touched.
3. Contract Adherence: Verify implementation meets all required functional, architectural, and safety constraints.
4. Compilation & Linting: Independently verify clean compilation, zero warnings under -D warnings, and 100% test passes.
5. Publish structured CLOUD_ROLE_RESULT v1 report to Issue/PR tracker or handoff log.
```

### Template C: Independent Executor Dispatch (with Cloud Teardown)
```markdown
You are the INDEPENDENT EXECUTOR subagent for Milestone <milestone_name>.

### Mission Context & Boundaries
- Target Environment: <local_or_remote_host>
- Candidate SHA: <candidate_sha>
- Request ID: <request_id>

### Execution Requirements
1. Checkout/sync candidate commit <candidate_sha> in target environment.
2. Verify all cryptographic pins (Cargo.lock, fixture digests, schema hashes).
3. Execute full test suite, formatting, and linters.
4. Record performance metrics (p99 latency, throughput, memory HWM).
5. AUTOMATED TEARDOWN MANDATE:
   If running on billable cloud infrastructure (e.g. AWS EC2), execute shutdown (sudo shutdown -h now) immediately upon completion.
6. Publish authoritative EXECUTOR report with complete logs.
```

### Template D: Architect / Design Owner Dispatch
```markdown
You are the ARCHITECT subagent for Proposal <proposal_name>.

### Mission Context & Boundaries
- Target Directory: docs/phase-0/proposals/ (or docs/adr/)
- Base Architecture: <base_architecture_doc>
- Request ID: <request_id>

### Objectives & Deliverables
1. Draft or remediate the architectural proposal document: <doc_name>.
2. Define exact state machine transitions, error domains, and failure recovery.
3. Specify quantitative acceptance thresholds (p99 latency, memory caps, timeouts).
4. Strictly do NOT mutate production source code.
5. Return candidate architectural document with diff and rationale.
```

### Template E: Dynamic / Novel Custom Role Dispatch
```markdown
You are the <CUSTOM_ROLE_NAME> subagent for Task <task_name>.

### Role Authority Tier
- Authority Class: <AUTHORING_TIER | AUDIT_EXECUTION_TIER>
- Single Responsibility: <exact_crisp_single_mission>

### Mission Context & Boundaries
- Repository: <repo_name>
- Branch: <branch_name>
- Baseline SHA: <start_sha>
- Request ID: <request_id>

### Allowed Paths
- <path_1>
- <path_2>

### Forbidden Paths
- All paths outside the allowed list.

### Objectives & Specific Deliverables
1. <objective_1>
2. <deliverable_format>
3. Stop condition: Return structured report with evidence and findings. Do not perform out-of-scope actions.
```

---

## 4. Remediation Cycle Protocol

When a Reviewer or Executor reports blocking findings (`BLK-001`):
1. **DO NOT** terminate the Implementor.
2. **DO NOT** spawn a new Implementor from scratch.
3. Formulate the exact finding, line citations, and authorized remediation boundaries.
4. Send the remediation directive directly to the active Implementor using `send_message`:
   ```markdown
   ### REMEDIATION REQUEST: <finding_id>
   The Independent Reviewer identified blocking issue <finding_id>:
   - File: <file_path>:<lines>
   - Summary: <summary>
   - Authorized Remediation: <exact_fix_guidance>
   Please apply this fix, verify tests locally, commit, push, and report the new candidate SHA.
   ```
5. Await the remediated candidate SHA.
6. Dispatch the **same Reviewer** (preserving review continuity and focusing validation on what changed, rather than a fresh reviewer re-auditing the entire baseline) to verify the remediation diff.

> [!NOTE]
> **Reviewer Continuity Mandate**: In projects with strict audit standards (such as TTE or safety-critical PR workflows), re-checks must be routed back to the *same* Reviewer who identified the initial findings. Spawning a fresh reviewer leads to contradictory scope evaluations and invalidates previous sign-offs.

---

## 5. Lifecycle & Cost Governance Checklist

- [ ] **Exact Bounding**: Subagent prompt contains Request ID, Start SHA, Allowed Paths, and Stop Conditions.
- [ ] **Role Guardrails Respected**: If a novel custom role is spawned, it has a single responsibility and declared authority class (Authoring vs Audit).
- [ ] **Reactive Waiting**: Subagents launched asynchronously; coordinator yields turn immediately with zero status polling loops.
- [ ] **Continuation Reuse**: Remediation handled via `send_message` to the existing agent.
- [ ] **Immediate Teardown**: Idle subagents terminated via `manage_subagents(Action="kill_all")` upon report receipt.
- [ ] **Cloud Safety**: Remote compute (EC2/GCP) automatically shut down upon test completion.
- [ ] **Dual-Gate Attestation**: Milestone accepted only after independent Reviewer (PASS) and Executor (PASS) verification.
- [ ] **Exact-SHA Recording**: Milestone acceptance records immutable Git commit SHA.

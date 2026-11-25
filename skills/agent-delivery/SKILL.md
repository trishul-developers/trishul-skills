---
name: agent-delivery
description: One-driver delivery workflow for multi-model software work. A single driver session plans, briefs, dispatches and judges; every other role (architect, implementor, maths implementor, reviewers, phase reviewer, light worker, scout, advisor) is a fresh worker started from a brief file, either as a native subagent or as a headless Codex, Antigravity or Claude run. Roles map to configurable provider/model/effort slots with a fallback chain spread across Claude, Codex and Antigravity, reviews are forced onto a different model family, and a run log in the repository lets any session resume. Use when driving phased implementation, reviews and rulings without standing agent chats or a message hub.
compatibility: Python 3 standard library. Headless providers need the sibling codex-headless, agy-headless, claude-headless and (for WSL Antigravity) agy-wsl-headless skills installed next to this one.
tags: [orchestration, delivery, roles, headless, codex, antigravity, claude, review]
---

# Agent Delivery

One driver, many fresh workers, one run log. No standing chats, no hub, no relays.

## The model

- **The driver** is the session the owner talks to. It plans, writes briefs, dispatches workers, judges what comes back, keeps the run log and asks the owner for merges. **It does not do the work**: code, investigations, test runs and fixes go to workers. Reading results and deciding is the job. Keep turns short so the owner can always reach you.
- **Workers** are started fresh for one job and exit. **The brief is everything a worker gets**: what it owns, what it must not touch, what it needs that it can't easily find, and what done looks like. A brief that assumes context produces a worker that invents it.
- **Roles** are defined in the project's profile, `<repo>/.agent-delivery.json` (found automatically; start from `profiles/example.json`): what each role is for, which roles must be cross-provider, the project rules and governing docs. The skill itself is generic.
- **Models** are the user's, not the project's or the skill's. They live in a local file, `~/.agent-delivery/models.json` (override the path with `AGENT_DELIVERY_MODELS`), under `default` for every project and `projects.<name>` for one. That file overrides any model slots in the project profile. Each role gets a primary slot and a `fallbacks` list, ideally spread across providers. The owner or the driver changes models as needs change: `delivery.py models show`, `delivery.py models set ROLE --primary provider:model:effort[:sandbox|mode] --fallback-slot ... [--all-projects]`. Model ids must match what each CLI lists (`agy models` shows Antigravity's).
- **State has two homes.** Local working state lives in `<repo>/<run_dir>` (untracked): the run log (`runlog.jsonl`, every dispatch, verdict, merge and decision with step, model, thread id and usage), briefs, worker reports and run folders. It is free, fast and noise-free, and it is what a new session resumes from (`status`). GitHub holds the durable record, written only at milestones: the PR description (scope, test counts, differential note, reviewer verdict and model), architect rulings and questions as issue comments or docs PRs, and phase evidence and ACCEPTED on the phase issue. The rule is that anything another person, another machine or a cloud agent must see, or that must survive a disk loss, goes to GitHub. Everything else stays local.

### Session layout (optional manager tier)

For a long multi-phase project, run the driver as a phase-scoped chat under a persistent manager:

| Tier | Session | Lifetime | Job |
|---|---|---|---|
| Manager | the owner's main chat | persistent | Starts each phase's orchestrator and phase architect as child sessions, handles owner gates, plans across phases, archives phase chats when the phase completes. Not in the step loop. |
| Chief architect | child session, consulted only on cross-phase rules | role persistent, chat replaceable | Contracts and decisions that span phases. Keeps its state in docs and memory, so a new chat can take over. |
| Phase architect | child session, new per phase | one phase | Phase specs and rulings; recommends acceptance. |
| Orchestrator (this skill's driver) | child session, new per phase | one phase | Runs the loop below with subagents and headless workers. |
| Workers | subagent or headless run | one job | Implement, review, scout. |

- The orchestrator and the phase architect talk directly by session id; the manager is not a relay. Each contacts the manager only for phase end, blockers and owner gates.
- A child session's turn-end note goes to whoever started it, so a reply meant for a sibling must be sent to that sibling's session id.
- Before a chat is replaced or archived, it writes its state (branches, PRs, open questions, decisions, next step) to memory or docs.
- The project profile's `sessions` block lists these tiers with their default models. They are chats, not `run` roles.

Providers:
| Provider | How it runs |
|---|---|
| `claude-native` | The driver starts a fresh subagent on the slot's model with the brief as its prompt. With `--headless`, runs `claude -p` instead (for a non-Claude driver). |
| `codex` | `codex-headless`, with the slot's model, effort and sandbox. |
| `agy` | `agy-headless`, with the slot's model, effort and mode. |
| `agy-wsl` | `agy-wsl-headless`: the same Antigravity CLI run inside WSL, which has its own quota. Same slot syntax as `agy` (`agy-wsl:gemini-4-hydrogen-high:high`). Needs `wsl.exe` and a signed-in `agy` in WSL. The runner tells the worker to use `git.exe` (and `"/mnt/c/Program Files/dotnet/dotnet.exe"` if needed), always with `</dev/null`, because native WSL git cannot read Windows worktrees and WSL has no git-lfs or dotnet. It runs with `--output-format json`, so the thread id is the Antigravity conversation id; its `ok`/`failed` status is logged as `success`/`error`. |
| `claude-advisor` | The driver's built-in advisor tool if it has one; otherwise `claude -p` with `--headless`. |

## Commands

The script is `scripts/delivery.py`. Pass the main checkout as `-C` (not a worktree), so there is one run log; the profile is read from it:

```bash
python "<skill>/scripts/delivery.py" -C "<repo>" roles -v
python "<skill>/scripts/delivery.py" -C "<repo>" status
python "<skill>/scripts/delivery.py" -C "<repo>" brief implement --set step=G03a.04 --set title=Navigation --set worktree=... --set branch=... --set paths=... --set task=... --set spec_ref=... --set done=...
python "<skill>/scripts/delivery.py" -C "<repo>" run implementor --step G03a.04 --brief <brief.md> --cwd <worktree>
python "<skill>/scripts/delivery.py" -C "<repo>" run reviewer --step G03a.04 --implemented-by claude --brief <review.md>
python "<skill>/scripts/delivery.py" -C "<repo>" done implementor --step G03a.04 --status ok --tokens 211000 --minutes 104 --report <report.md>
python "<skill>/scripts/delivery.py" -C "<repo>" brief recheck --set step=G03a.04 --set round=2 --set branch=... --set worktree=... --set prev_head=<sha> --set head=<sha> --set fixes=...
python "<skill>/scripts/delivery.py" -C "<repo>" run reviewer --implemented-by claude --brief <recheck.md> --resume <thread>
python "<skill>/scripts/delivery.py" -C "<repo>" log verdict --set step=G03a.04 --set verdict=PASS --set sha=<sha>
```

- `brief` writes a `.meta.json` beside the brief (step, worktree, branch, head, round). `run` takes `--step` and `--cwd` from it when they aren't passed, so writers and reviewers run in the worktree, not the main checkout. It warns when a worktree role would run in the main checkout.
- `done` logs the completion of a native subagent job (status, tokens, minutes, report, round), which the script can't observe itself. The native `run` output prints the exact `done` command to use. After a SendMessage follow-up to the same subagent, log it again with `done ... --followup`.
- `run --auto-approve` (agy and agy-wsl only) passes `--dangerously-skip-permissions` so a headless implementor can run tests and commit. It is never a slot default: use it only with the owner's OK, and keep the worker in its worktree. The run event records `auto_approve: true`. Child runs get `PYTHONIOENCODING=utf-8`. For long implementor runs, raise `--timeout` (seconds; default 3600).
- A recheck uses the `recheck` template on the same thread (`--resume`). It reads only `prev_head..head`, because the thread already holds the first review. The log records `resume=same-thread`.

- `brief` refuses to write a brief with unfilled `{{fields}}`. Rules and governing docs from the profile are filled in for you. Use `--set-file key=path` for long text.
- `run` on a headless provider runs it now and prints the thread id, run folder and usage. On `claude-native` it prints the model and brief for you to start with your subagent tool. Run long headless jobs in the background so their exit wakes you.
- `--implemented-by <family>` (`claude`, `codex`, `gemini`) makes a `cross_provider` role skip slots of that model family. Family follows the model, not the CLI: Claude models hosted on Antigravity count as `claude`. If no independent slot is left, it warns and uses a fresh same-family worker.
- `--fallback` takes the next slot in the chain; repeat it (`--fallback --fallback`) to go further. Use it when a provider is out of quota.
- `--dry-run` checks the command without spending quota, and logs nothing.

## The loop

1. **Orient.** `status`, then the repository status (`git fetch`, open PRs, CI). Read the spec rows for the next step.
2. **Split.** One worker per step, per file set or per question. Name who owns which paths before anyone starts. Two workers in the same files is the failure to design out. Writers each get their own worktree; reviewers read only.
3. **Brief and dispatch.** `brief` then `run`. Implementation uses `implementor`, or `maths-implementor` for steps flagged maths.
4. **Judge.** Read the worker's report and check its claims: a fresh, non-zero test run; CI per job; the diff matches the owned paths. Send work back with the exact gap, or pass it on.
5. **Review.** Start the reviewer with `--implemented-by` set to whoever implemented. One joint review of tests and code. Blockers go back to the implementor; the **same reviewer thread** rechecks only what changed (`--resume`).
6. **Land.** Push, wait for CI, open the PR, and ask the owner to merge with the PR number and a one-line reason. Log the verdict and the merge.
7. **Report** to the owner in a few lines, and go round again.

Verifiers: the ratio of one reviewer per two to four implementors sizes parallel capacity only. Each batch still gets its own fresh review thread, and that same thread does the recheck. A reviewer reports and the author fixes; a reviewer that fixes puts two writers in the same files.

Refer to earlier results by path or run-log entry (the report file, the review file, the thread id). Do not paste one worker's report into another's brief; point to it.

## Why one driver and no middle manager

There is no coordinator layer between the driver and the workers. The driver is the coordinator. A standing middle manager would repeat the driver's context, add a relay hop to every decision, and bring back the friction this skill removes: duplicated reasoning between manager and architect, messages copied between sessions, and a chat that can be archived mid-phase.

What a manager would add, the skill gets more cheaply:
- **Small driver context:** briefs and reports live in files and the run log, and the driver reads summaries, not transcripts.
- **Parallel dispatch:** the driver starts several workers at once in disjoint worktrees.
- **Planning help:** for a large phase, the driver may start a one-off `architect` or `light-worker` job to split the work into briefs. That is a worker, not a layer.

Revisit only if the driver's context, not the workers', becomes the measured bottleneck.

A manager above the driver (see Session layout) is different: it works at phase granularity and never sits between the driver and a worker.

## Roles in a profile

Typical roles (`profiles/example.json` has all of these):
- `driver`: you.
- `architect`: specs and rulings, fresh context per ruling, output lands as a docs PR or issue comment. Material product or authority changes stop at a recommendation for the owner.
- `implementor`, `maths-implementor`: code and tests for one step.
- `reviewer` (Tier 1 and determinism evidence), `reviewer-light` (Tier 2 and 3), `phase-reviewer`: always cross-provider, never the implementor's context.
- `light-worker`: docs, builds, chores. `scout`: shortlists and research, verified afterwards.
- `advisor`: see below.

An implementor never accepts its own work. The architect records acceptance from the phase review.

## Advisor

The advisor is the strongest available model, used for advice only and only for the hardest questions:
- a contract conflict the architect can't settle from the documents;
- a design fork with a large cost either way;
- a problem still failing after 2 fix rounds.

Only the driver (acting as manager) and the architect call it (`callers` in the profile). The slot model `builtin` means the agent's own advisor tool, which picks a model stronger than the driver; name a model only if the owner chooses one. Use the `advise` template: the question, what was tried, the fixed constraints and the few files to read. Weigh the advice seriously. If your evidence contradicts it, put the conflict back to the advisor once rather than silently switching. Log each advisor call.

## Quota and fallback

- When a provider runs out, rerun the job with `--fallback` (again for the second fallback). Don't wait for quota, and say on the PR which model did the work.
- A worker that dies on quota mid-job keeps its branch: start the fallback with a brief that points at the branch and the last report, so it continues rather than restarts.
- Keep headless briefs tight: the step or diff, its spec rows, the paths to read. Never paste whole specs or histories.
- Record thread ids and usage (the run log does this) so cost per phase is visible.

## Rules that always hold

- One writer per worktree. Serial access to any machine-wide tool (for example, one Unity process at a time, as the profile says).
- Workers do not push, open PRs or merge unless their brief says so. The driver commits by explicit path.
- No secrets, tokens or session handles in briefs, logs or commits.
- Treat test and CI claims as unverified until checked.
- Settings, hooks, MCP servers and connectors are the owner's to change. List proposed changes for approval; never change them silently.

## Templates

`templates/implement.md`, `review.md`, `recheck.md`, `phase-brief.md` (manager to phase orchestrator), `phase-review.md`, `ruling.md`, `advise.md`. Copy and adapt them per project if needed; pass a path to `brief` to use your own.

## Borrowed from Antigravity's swarm

- **The coordinator does not do the work.** It briefs, judges and stays reachable.
- **The brief is everything.** Workers start cold, so a brief names what they own, what not to touch, what they need and what done looks like.
- **Design out shared files.** Give each file one owner, split along file or question boundaries, and give each writer its own workspace.
- **Verifiers report, authors fix.** Run about one verifier per two to four authors.
- **Point, don't paste.** Refer to earlier results by reference (here a file path or run-log entry), not by copying them between workers.
- **Stay lean.** Every worker costs tokens. Add one only when work is queued and nobody is free.
- **Out of quota: switch model and continue.** Don't stop the job.
- **Durable shared record.** The swarm's board outlives turns. Here the run log and GitHub do that job.

Left out: the always-on message board and standing workers asleep on it. Headless one-shot runs are cheaper for this kind of work, and need no wake plumbing.

## Using it from another agent

Claude is the driver today. Any agent that can run Python can drive with this skill later. A non-Claude driver passes `--headless` so `claude-native` roles run through `claude -p`. Known gap: that path passes no tool permissions yet, so a headless Claude implementor can't edit files; use it for read-only roles until it does. Give it its own profile, or edit the slots, so the driver's own provider isn't also the reviewer of its own work.

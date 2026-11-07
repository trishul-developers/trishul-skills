---
name: codex-cli
description: Send a task to the OpenAI Codex CLI with a chosen model and reasoning effort, wait for Codex to finish, and get its answer back. Use this whenever the user wants to hand work to Codex or GPT-6 (Sol, Terra, Astra, Luna), run something through the codex command or Codex CLI, get a second opinion, code review or implementation from Codex, pick a Codex model or effort level (low, medium, high, xhigh, max, ultra), continue an earlier Codex thread, or says things like "ask codex", "send it to codex", "have codex do X", "codex exec", or "run this on codex and wait". Also use it when Claude should delegate a coding or research sub-task to Codex and needs the result before going on, even if the user never names the tool.
compatibility: Requires the Codex CLI (`codex`) on PATH and signed in with a ChatGPT account, plus Python 3 for the runner script. Tested with codex-cli 0.166.0 on Windows.
---

# Codex CLI task runner

This skill sends one task to `codex exec`, waits until Codex finishes, and prints its final message. The runner is `scripts/codex_task.py` (stdlib-only Python). It handles the parts that are easy to get wrong by hand: passing the prompt safely, choosing the model and effort, timing out cleanly, killing leftover processes, and keeping a record of each run.

For Antigravity (agy) instead of Codex, use the `agy-cli` skill.

## Run a task

1. Write the brief to a file, such as `<scratchpad>/brief.md`. Make it self-contained: the goal, the files or paths involved, constraints, what done looks like, and what to report back. Codex starts with no memory of this conversation, so anything it needs must be in the brief.
2. Run the runner with the prompt file:

```bash
python "$HOME/.claude/skills/codex-cli/scripts/codex_task.py" -m gpt-6.1-sol -e high -s workspace-write -C "E:/Projects/trishul-tactical-engine" --timeout 1800 --prompt-file "<scratchpad>/brief.md"
```

3. The command blocks until Codex is done. stdout is Codex's final message, and stderr ends with one status line that names the run folder and the thread id.
4. Read the answer, then check the work yourself (see "After it returns").

Defaults if you omit flags: model `gpt-6.1-sol`, effort `high`, sandbox `workspace-write`, timeout 1800 s, working directory the current folder.

For a quick question, a short prompt also works: pass the text as an argument, or pipe it with `-`.

## Choose the model and effort

Models that show in the Codex picker (from `codex debug models`, checked 2026-11-03):

| Model | Efforts available | Notes |
|---|---|---|
| `gpt-6.1-sol` | low, medium, high, xhigh, max, ultra | Default. Strongest coding model. |
| `gpt-6.1-terra` | low, medium, high, xhigh, max, ultra | |
| `gpt-6-astra` | low, medium, high, xhigh, max, ultra | |
| `gpt-6-sol` | low, medium, high, xhigh, max, ultra | |
| `gpt-6-luna` | low, medium, high, xhigh, max | No ultra. Lighter and cheaper. |
| `gpt-5.6-sol`, `gpt-5.6-terra` | low to ultra | Older generation |
| `gpt-5.6-luna` | low, medium, high, xhigh, max | Older generation, lighter |

Do not use the hidden models (`gpt-6-chat-thinking`, `gpt-reserve`, `codex-auto-review`).

Effort guidance:
- `low` or `medium`: quick questions, small edits, summaries.
- `high` (default): normal implementation and debugging.
- `xhigh` or `max`: hard design or subtle bugs, when the user asks for depth.
- `ultra`: maximum reasoning plus automatic task delegation. It costs much more quota. Use it only when the user asks for it.

Every run uses the user's ChatGPT plan quota, so match the effort to the task rather than defaulting to the top.

## Choose the sandbox

- `read-only`: review, analysis and answering questions. Codex can read files but not change them.
- `workspace-write` (default): implementation. Codex can edit files under the working directory and run commands there.
- `danger-full-access`: only when the user explicitly approves it. The runner refuses this unless you also pass `--allow-full-access`.

Pick the narrowest sandbox that lets the task finish.

## Wait and timing

The runner blocks until Codex finishes or `--timeout` expires. A timeout kills Codex and its child processes and exits with code 124.

The Bash tool stops foreground commands after 10 minutes. For a task that may take longer, run the same command with `run_in_background: true` and wait for the completion notification. Do not poll or sleep in a loop while it runs.

## Continue a thread

Each run prints a `thread=<id>` value and records it in `result.json`. To send a follow-up in the same thread, reuse the id:

```bash
python "$HOME/.claude/skills/codex-cli/scripts/codex_task.py" -m gpt-6.1-sol -e high --resume <thread-id> --prompt-file "<scratchpad>/followup.md"
```

A resumed run keeps the original sandbox and folder. `--sandbox` and `--cwd` are ignored when resuming.

## After it returns

- Codex's report is a claim, not proof. For implementation tasks, read the changes with `git diff` (or the files directly) and run the relevant tests yourself before telling the user the work is done.
- The run folder (printed on stderr) holds `prompt.md`, `last_message.md`, `events.jsonl`, `stderr.log` and `result.json`. Use it to see exactly what was sent and what came back.
- Report the model, effort, sandbox, duration and any token usage from `result.json`. Do not present the Codex answer as verified unless you checked it.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. The final message is on stdout. |
| 124 | Timed out. Codex and its children were killed. |
| 2 | Bad input: no prompt, missing file, or Codex not on PATH. |
| other | Codex failed. The tail of its stderr is printed. Check `stderr.log` in the run folder. |

## Gotchas

- Use Windows-style absolute paths for `--cwd` and `--image`, such as `E:/Projects/repo`. A Git Bash path like `/tmp/x` is not an absolute Windows path.
- A folder that is not a git repository works. The runner adds `--skip-git-repo-check` only in that case.
- Long briefs belong in a file. Command-line length limits and shell quoting break long inline prompts.
- Passing `--dry-run` prints the exact Codex command and uses no quota. Use it to check flags before a real run.

## Verified on this machine

Run on 2026-11-03 with codex-cli 0.166.0:
- A low-effort read-only task returned its answer in about 13 seconds. Token usage was recorded.
- `--resume` continued the same thread.
- A forced 3-second timeout ended with exit code 124 and status `timeout`.
- A workspace-write task created a file in a folder that is not a git repository.

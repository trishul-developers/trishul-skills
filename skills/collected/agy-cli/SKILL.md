---
name: agy-cli
description: Send a task to the Antigravity CLI (agy, Gemini and other models) with a chosen model and reasoning effort, wait for the turn to finish, and get the answer back. Use this whenever the user wants to hand work to Antigravity or agy, run something through the agy command, get a Gemini 3.8 Flash answer or second opinion, use Antigravity for mechanical or Unity-operator style work, pick an agy model or effort level (low, medium, high, xhigh, max), continue an earlier agy conversation, or says things like "ask agy", "send it to antigravity", "run this on agy and wait", or "use gemini flash for this". Also use it when Claude should delegate a sub-task to Antigravity and needs the result before going on, even if the user never names the tool.
compatibility: Requires the Antigravity CLI (`agy`) on PATH and signed in to Antigravity, plus Python 3 for the runner script. Tested with agy 1.4.12 on Windows.
---

# Antigravity (agy) task runner

This skill sends one task to `agy` in print mode, waits until the turn finishes, and prints the response. The runner is `scripts/agy_task.py` (stdlib-only Python). It passes the prompt safely, sets the model and effort, times out cleanly, kills leftover processes, and records each run.

For OpenAI Codex instead, use the `codex-cli` skill.

## Expect long turns

Print mode is slow to start. In testing on 2026-11-03, even a one-word reply took about 200 seconds, and a file-read task took about 200 seconds too. The first call in a session is usually the slowest. Plan for a few minutes per turn, and use the background pattern below for anything more than a quick question.

## Run a task

1. Write the brief to a file, such as `<scratchpad>/brief.md`. Make it self-contained: the goal, the files or paths involved, constraints, what done looks like, and what to report back. The agent starts with no memory of this conversation.
2. Run the runner with the prompt file:

```bash
python "$HOME/.claude/skills/agy-cli/scripts/agy_task.py" -m gemini-3.8-flash -e medium -C "E:\Projects\trishul-tactical-engine" --timeout 1800 --prompt-file "<scratchpad>/brief.md"
```

3. The command blocks until the turn finishes or `--timeout` expires. stdout is the response text, and stderr ends with one status line that names the run folder and the conversation id.
4. Read the answer, then check the work yourself (see "After it returns").

Defaults if you omit flags: model `gemini-3.8-flash`, effort `medium`, timeout 1800 s, working directory the current folder.

Prompts over about 20,000 characters are not sent inline. The runner writes them to the run folder and sends a short instruction that points at the file, so Windows command-line length limits do not matter.

## Choose the model and effort

Models come from `agy models`. As of 2026-11-03 the list includes:

| Model | Effort | Notes |
|---|---|---|
| `gemini-3.8-flash` | low, medium, high, xhigh, max | Default. Set the level with `--effort`, not in the model name. |
| `claude-sonnet-4-6` | | Claude model served through Antigravity |
| `claude-opus-4-6-thinking` | | Claude model served through Antigravity |
| `gpt-oss-120b-medium` | | Open-weight model served through Antigravity |

Run `agy models` again before relying on this table, since the list changes. In testing, `--model gemini-3.8-flash --effort low` was resolved by agy to `gemini-3.8-flash-low`, so the effort is applied through the model alias.

Effort guidance:
- `low`: quick answers, lookups, checks.
- `medium` (default): routine mechanical work and summaries.
- `high` and above: harder reasoning. These take longer, so set the timeout to match.

## Permissions

With default permissions, print mode in testing could read a file in the working folder and create a new file there without any extra flag. Shell commands were not tested under default permissions, so treat them as unverified until you test them.

Pass `--auto-approve` only when the user has approved the tools a task needs, because it lets the agent run any tool without asking. `--mode plan` is a lighter option when the task should only plan.

## Background pattern

Because a turn often takes several minutes, run the runner with `run_in_background: true` and wait for the completion notification. Do not poll or sleep while it runs. The Bash tool's foreground limit is 10 minutes, so anything you expect to run longer must go in the background.

## Continue a conversation

Each run records `conversation_id` in `result.json` and prints it on stderr. To send a follow-up in the same conversation:

```bash
python "$HOME/.claude/skills/agy-cli/scripts/agy_task.py" -m gemini-3.8-flash -e medium --resume <conversation-id> --prompt-file "<scratchpad>/followup.md"
```

## After it returns

- The response is the agent's claim, not proof. For any file change, read the files or `git diff`, and run the relevant tests yourself before telling the user the work is done.
- The run folder (printed on stderr) holds `prompt.md`, `response.md`, `result.json`, `agy.log` and `stderr.log`. If a run hangs or returns nothing, `agy.log` shows what agy was doing.
- Report the model, effort, duration and token usage from `result.json`. Do not present the answer as verified unless you checked it.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. The response is on stdout. |
| 124 | Timed out. agy and its children were killed. |
| 2 | Bad input: no prompt, missing file or folder, or agy not on PATH. |
| 1 | The turn failed. The tail of stderr is printed. Check `agy.log` in the run folder. |

## Gotchas

- Use Windows-style absolute paths for `-C`, such as `E:\Projects\repo`. Git Bash paths like `/tmp/x` are not absolute to a Windows program. agy then logs "GeminiDir must be absolute" and can behave unpredictably.
- agy's logs say "not logged into Antigravity" during startup even on successful runs. This is background noise. The run is fine if `status` is `ok`.
- Configured MCP servers start with the CLI and add delay. In the test runs, a `unity-mcp` server was still connecting at the 90-second mark. The runner does not disable MCP servers, because changing them is a persistent setting the user has not approved.
- Use `--dry-run` to print the exact agy command without spending quota.

## Verified on this machine

Run on 2026-11-03 with agy 1.4.12:
- A `gemini-3.8-flash` low-effort prompt with quotes and a newline returned `PONG` with status `ok` (about 205 seconds).
- Reading a file in the working folder under default permissions returned the file contents.
- A forced timeout ended with exit code 124.

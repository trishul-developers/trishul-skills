#!/usr/bin/env python3
"""Send one task to the Antigravity CLI (agy), wait for the turn to finish, and print its answer.

Standard library only. Works from Git Bash, PowerShell or cmd.

stdout  the final response text from agy (empty if the turn did not succeed)
stderr  one status line: status, model, effort, duration, and the run folder
exit    0 success | 124 timed out | 2 bad input or agy not found | 1 turn failed

Every run writes its files to a run folder (default: <temp>/agy-runs/<stamp>-<id>):
  prompt.md      the exact prompt sent
  response.md    agy's final response
  result.json    status, timing, model, effort, conversation id, token usage
  agy.log        agy's own log for the run (--log-file), useful when a run hangs
  stderr.log     agy's stderr
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_EFFORT = "medium"
DEFAULT_TIMEOUT = 1800  # seconds; a single agy turn can take several minutes to start
EFFORTS = ("low", "medium", "high", "xhigh", "max")
MODES = ("accept-edits", "auto", "plan")
# Windows caps a process command line at about 32k characters; longer briefs go through a file.
MAX_INLINE_PROMPT = 20000
EXIT_TIMEOUT = 124
EXIT_USAGE = 2
EXIT_FAILED = 1


def fail(message: str, code: int = EXIT_USAGE) -> None:
    print(f"agy_task: {message}", file=sys.stderr)
    sys.exit(code)


def read_prompt(args: argparse.Namespace) -> str:
    """Return the prompt text from --prompt-file, the positional text, or stdin ('-')."""
    if args.prompt_file:
        path = Path(args.prompt_file)
        if not path.is_file():
            fail(f"prompt file not found: {path}")
        return path.read_text(encoding="utf-8")
    if args.prompt == "-":
        return sys.stdin.read()
    if args.prompt:
        return args.prompt
    fail("no prompt given: pass --prompt-file FILE, a prompt string, or '-' for stdin")
    return ""  # unreachable; fail() exits


def kill_tree(proc: subprocess.Popen) -> None:
    """Stop agy and the language server it started, so a timed-out run leaves nothing behind."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def build_command(args: argparse.Namespace, agy: str, prompt_arg: str, log_path: Path) -> list[str]:
    # `-p=<text>` must be one argument: a bare `-p` takes the next token as its value,
    # so `-p --model ...` mis-reads the flags as the prompt.
    cmd = [agy, f"-p={prompt_arg}", "--model", args.model, "--effort", args.effort]
    cmd += ["--output-format", "json", "--log-file", str(log_path)]
    if args.resume:
        cmd += ["--conversation", args.resume]
    if args.mode:
        cmd += ["--mode", args.mode]
    if args.auto_approve:
        cmd.append("--dangerously-skip-permissions")
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one Antigravity (agy) print-mode task with a model and effort, and wait for its answer.",
    )
    parser.add_argument("prompt", nargs="?", help="Task text, or '-' to read it from stdin.")
    parser.add_argument("--prompt-file", help="Read the task from this file (preferred for long briefs).")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"agy model (default {DEFAULT_MODEL}).")
    parser.add_argument(
        "-e", "--effort", default=DEFAULT_EFFORT, choices=EFFORTS,
        help=f"Reasoning effort (default {DEFAULT_EFFORT}).",
    )
    parser.add_argument("--mode", choices=MODES, help="agy execution mode (accept-edits, auto, plan). Default: agy's own.")
    parser.add_argument(
        "--auto-approve", action="store_true",
        help="Auto-approve every tool call (agy --dangerously-skip-permissions). Default permissions allowed "
             "file reads and writes in testing; use this for shell or other tools, and only for tasks the user has approved.",
    )
    parser.add_argument("-C", "--cwd", default=".", help="Working directory for agy (default: current directory).")
    parser.add_argument("--resume", metavar="CONVERSATION_ID", help="Continue an earlier run (conversation_id from result.json).")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Seconds to wait (default {DEFAULT_TIMEOUT}).")
    parser.add_argument("--out-dir", help="Run folder to write into (default: a new folder under the temp directory).")
    parser.add_argument("--dry-run", action="store_true", help="Print the command that would run and exit; uses no quota.")
    args = parser.parse_args()

    prompt = read_prompt(args)
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        fail(f"working directory not found: {cwd}")

    agy = shutil.which("agy")
    if agy is None and not args.dry_run:
        fail("the 'agy' command is not on PATH. Install the Antigravity CLI or fix PATH.")
    agy = agy or "agy"

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.gettempdir()) / "agy-runs" / f"{stamp}-{uuid.uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = run_dir / "prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    log_path = run_dir / "agy.log"
    stderr_path = run_dir / "stderr.log"
    stdout_path = run_dir / "stdout.json"
    result_path = run_dir / "result.json"

    if len(prompt) > MAX_INLINE_PROMPT:
        # Hand agy a pointer to the file instead of the whole brief. Reading a file worked
        # under default permissions in testing, so no approval flag is needed for this.
        prompt_arg = (
            f"Your full task is in the file {prompt_path}. Read it completely and carry it out exactly as written."
        )
    else:
        prompt_arg = prompt

    cmd = build_command(args, agy, prompt_arg, log_path)
    if args.dry_run:
        printable = " ".join(f'"{c}"' if " " in c or "\n" in c else c for c in cmd)
        print(printable[:4000] + (" ...(truncated)" if len(printable) > 4000 else ""))
        print(f"(cwd: {cwd}; prompt is {len(prompt)} chars saved to {prompt_path})")
        return 0

    started = time.monotonic()
    timed_out = False
    with open(stdout_path, "wb") as out_file, open(stderr_path, "wb") as err_file:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=out_file,
            stderr=err_file,
            start_new_session=(os.name != "nt"),
        )
        try:
            proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(proc)
            proc.wait()
    duration = round(time.monotonic() - started, 1)

    raw = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
    payload: dict = {}
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
    response = str(payload.get("response") or "")
    agy_status = str(payload.get("status") or "")
    conversation_id = payload.get("conversation_id") or args.resume

    if timed_out:
        status = "timeout"
    elif proc.returncode == 0 and agy_status == "SUCCESS" and response.strip():
        status = "ok"
    else:
        status = "error"

    response_path = run_dir / "response.md"
    response_path.write_text(response, encoding="utf-8")
    result = {
        "status": status,
        "agy_status": agy_status or None,
        "exit_code": EXIT_TIMEOUT if timed_out else proc.returncode,
        "model": args.model,
        "effort": args.effort,
        "mode": args.mode,
        "auto_approve": args.auto_approve,
        "cwd": str(cwd),
        "conversation_id": conversation_id,
        "resumed": bool(args.resume),
        "num_turns": payload.get("num_turns"),
        "duration_seconds": duration,
        "agy_duration_seconds": payload.get("duration_seconds"),
        "usage": payload.get("usage"),
        "run_dir": str(run_dir),
        "timeout_seconds": args.timeout,
    }
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if status == "ok":
        sys.stdout.write(response if response.endswith("\n") else response + "\n")
    else:
        tail = stderr_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-15:]
        print("\n".join(tail), file=sys.stderr)

    print(
        f"agy_task: status={status} model={args.model} effort={args.effort} "
        f"duration={duration}s conversation={conversation_id} run_dir={run_dir}",
        file=sys.stderr,
    )
    if status == "timeout":
        return EXIT_TIMEOUT
    if status == "ok":
        return 0
    return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Send one task to the Codex CLI, wait for it to finish, and print its final message.

Standard library only. Works from Git Bash, PowerShell or cmd.

stdout  the final message from Codex (empty if Codex produced none)
stderr  one status line: status, model, effort, duration, and the run folder
exit    0 success | 124 timed out | 2 bad input or Codex not found | else Codex's exit code

Every run writes its files to a run folder (default: <temp>/codex-runs/<stamp>-<id>):
  prompt.md        the exact prompt sent
  last_message.md  Codex's final answer
  events.jsonl     the full JSON event stream from `codex exec --json`
  stderr.log       Codex's stderr
  result.json      status, timing, model, effort, thread id, token usage
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

DEFAULT_MODEL = "gpt-6.1-sol"
DEFAULT_EFFORT = "high"
DEFAULT_SANDBOX = "workspace-write"
DEFAULT_TIMEOUT = 1800  # seconds; Codex coding tasks often run for many minutes
EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
SANDBOXES = ("read-only", "workspace-write", "danger-full-access")
EXIT_TIMEOUT = 124
EXIT_USAGE = 2


def fail(message: str, code: int = EXIT_USAGE) -> None:
    print(f"codex_task: {message}", file=sys.stderr)
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


def is_git_repo(cwd: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def build_command(args: argparse.Namespace, codex: str, cwd: Path, last_message: Path) -> list[str]:
    cmd = [codex, "exec"]
    if args.resume:
        # `exec resume` keeps the original session's sandbox and directory.
        cmd += ["resume", args.resume]
    else:
        cmd += ["-s", args.sandbox, "-C", str(cwd)]
        if not is_git_repo(cwd):
            cmd.append("--skip-git-repo-check")
    cmd += ["-m", args.model, "-c", f'model_reasoning_effort="{args.effort}"']
    for image in args.image or []:
        cmd += ["-i", str(Path(image).resolve())]
    cmd += ["--json", "-o", str(last_message), "-"]  # "-" = read the prompt from stdin
    return cmd


def kill_tree(proc: subprocess.Popen) -> None:
    """Stop Codex and every process it started, so a timed-out run leaves nothing behind."""
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


def scan_events(events_path: Path) -> tuple[str | None, dict | None]:
    """Pull the thread id and the last reported token usage out of the JSON event stream."""
    thread_id = None
    usage = None
    if not events_path.exists():
        return thread_id, usage
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if thread_id is None:
            thread_id = event.get("thread_id") or event.get("session_id")
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
    return thread_id, usage


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one Codex CLI task with a model and reasoning effort, and wait for its answer.",
    )
    parser.add_argument("prompt", nargs="?", help="Task text, or '-' to read it from stdin.")
    parser.add_argument("--prompt-file", help="Read the task from this file (preferred for long briefs).")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Codex model slug (default {DEFAULT_MODEL}).")
    parser.add_argument(
        "-e", "--effort", default=DEFAULT_EFFORT, choices=EFFORTS,
        help=f"Reasoning effort (default {DEFAULT_EFFORT}). 'ultra' lets Codex delegate and costs more.",
    )
    parser.add_argument(
        "-s", "--sandbox", default=DEFAULT_SANDBOX, choices=SANDBOXES,
        help=f"Sandbox for new runs (default {DEFAULT_SANDBOX}). Ignored with --resume.",
    )
    parser.add_argument(
        "--allow-full-access", action="store_true",
        help="Required to use --sandbox danger-full-access. Only pass after the user approves it.",
    )
    parser.add_argument("-C", "--cwd", default=".", help="Working directory for Codex (default: current directory).")
    parser.add_argument("--resume", metavar="THREAD_ID", help="Continue an earlier run's thread id (from result.json).")
    parser.add_argument("--image", action="append", help="Attach an image file (repeatable).")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Seconds to wait (default {DEFAULT_TIMEOUT}).")
    parser.add_argument("--out-dir", help="Run folder to write into (default: a new folder under the temp directory).")
    parser.add_argument("--dry-run", action="store_true", help="Print the command that would run and exit; uses no quota.")
    args = parser.parse_args()

    if args.sandbox == "danger-full-access" and not args.allow_full_access:
        fail("refusing danger-full-access without --allow-full-access")
    if args.resume and args.image:
        fail("--image cannot be combined with --resume in this runner")

    prompt = read_prompt(args)
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        fail(f"working directory not found: {cwd}")

    codex = shutil.which("codex")
    if codex is None and not args.dry_run:
        fail("the 'codex' command is not on PATH. Install Codex CLI or fix PATH.")
    codex = codex or "codex"

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.gettempdir()) / "codex-runs" / f"{stamp}-{uuid.uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = run_dir / "prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    last_message = run_dir / "last_message.md"
    events_path = run_dir / "events.jsonl"
    stderr_path = run_dir / "stderr.log"
    result_path = run_dir / "result.json"

    cmd = build_command(args, codex, cwd, last_message)
    if args.dry_run:
        printable = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        print(printable)
        print(f"(cwd: {cwd}; prompt is {len(prompt)} chars saved to {prompt_path})")
        return 0

    started = time.monotonic()
    timed_out = False
    with open(events_path, "wb") as events_file, open(stderr_path, "wb") as stderr_file:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=events_file,
            stderr=stderr_file,
            start_new_session=(os.name != "nt"),
        )
        try:
            proc.communicate(input=prompt.encode("utf-8"), timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(proc)
            proc.communicate()
    duration = round(time.monotonic() - started, 1)

    thread_id, usage = scan_events(events_path)
    final_text = last_message.read_text(encoding="utf-8") if last_message.exists() else ""
    if timed_out:
        status = "timeout"
    elif proc.returncode == 0 and final_text.strip():
        status = "ok"
    else:
        status = "error"

    result = {
        "status": status,
        "exit_code": EXIT_TIMEOUT if timed_out else proc.returncode,
        "model": args.model,
        "effort": args.effort,
        "sandbox": None if args.resume else args.sandbox,
        "cwd": str(cwd),
        "thread_id": thread_id or args.resume,
        "resumed": bool(args.resume),
        "duration_seconds": duration,
        "usage": usage,
        "run_dir": str(run_dir),
        "timeout_seconds": args.timeout,
    }
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if final_text:
        sys.stdout.write(final_text if final_text.endswith("\n") else final_text + "\n")
    if status != "ok":
        tail = stderr_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-15:]
        print("\n".join(tail), file=sys.stderr)

    print(
        f"codex_task: status={status} model={args.model} effort={args.effort} "
        f"duration={duration}s thread={result['thread_id']} run_dir={run_dir}",
        file=sys.stderr,
    )
    if status == "timeout":
        return EXIT_TIMEOUT
    if status == "ok":
        return 0
    return proc.returncode or 1


if __name__ == "__main__":
    sys.exit(main())

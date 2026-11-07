#!/usr/bin/env python3
r"""Universal Headless Codex Runner.

Executes OpenAI Codex non-interactively via `codex exec`, captures events,
manages timeouts, guarantees clean process tree cleanup on Windows, and
records full audit artifacts in a timestamped run directory.

Outputs:
  stdout: Final text response / message from Codex (or structured JSON if configured)
  stderr: Single-line status summary and diagnostics if failed
  exit code:
    0: Success
    124: Execution timed out (process tree cleanly terminated)
    2: Configuration / argument error or codex binary missing
    Other: Non-zero exit code from codex
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
from typing import Dict, List, Optional, Tuple

DEFAULT_MODEL = "gpt-6.1-sol"
DEFAULT_EFFORT = "high"
DEFAULT_SANDBOX = "workspace-write"
DEFAULT_TIMEOUT = 1800  # 30 minutes
EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
SANDBOXES = ("read-only", "workspace-write", "danger-full-access")

EXIT_OK = 0
EXIT_TIMEOUT = 124
EXIT_USAGE = 2


def fail(message: str, code: int = EXIT_USAGE) -> None:
    print(f"codex_headless: ERROR: {message}", file=sys.stderr)
    sys.exit(code)


def read_prompt(args: argparse.Namespace) -> str:
    """Extract prompt from file, CLI argument, or stdin."""
    if args.prompt_file:
        p = Path(args.prompt_file)
        if not p.is_file():
            fail(f"Prompt file does not exist: {p}")
        return p.read_text(encoding="utf-8")
    if args.prompt == "-":
        return sys.stdin.read()
    if args.prompt:
        return args.prompt
    fail("No prompt provided. Specify inline text, --prompt-file FILE, or '-' for stdin.")
    return ""


def is_git_repo(path: Path) -> bool:
    try:
        res = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except FileNotFoundError:
        return False


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Recursively kill process tree to avoid orphaned subshells or compiler workers."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, AttributeError):
            proc.kill()


def parse_events(events_path: Path) -> Tuple[Optional[str], Optional[Dict]]:
    """Extract thread_id and token usage from codex --json stream."""
    thread_id = None
    usage = None
    if not events_path.exists():
        return thread_id, usage

    with open(events_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if thread_id is None:
                thread_id = evt.get("thread_id") or evt.get("session_id")
            if isinstance(evt.get("usage"), dict):
                usage = evt["usage"]
    return thread_id, usage


def build_command(
    args: argparse.Namespace,
    codex_bin: str,
    cwd: Path,
    last_message_file: Path,
) -> List[str]:
    cmd = [codex_bin, "exec"]

    if args.resume:
        cmd.extend(["resume", args.resume])
    elif args.fork:
        cmd.extend(["fork", args.fork])
    else:
        cmd.extend(["-s", args.sandbox, "-C", str(cwd)])
        if not is_git_repo(cwd):
            cmd.append("--skip-git-repo-check")

    if args.model:
        cmd.extend(["-m", args.model])

    if args.effort:
        cmd.extend(["-c", f'model_reasoning_effort="{args.effort}"'])

    if args.config:
        for cfg in args.config:
            cmd.extend(["-c", cfg])

    if args.worktree and not (args.resume or args.fork):
        cmd.append("--worktree")

    if args.add_dir:
        for extra_dir in args.add_dir:
            cmd.extend(["--add-dir", str(Path(extra_dir).resolve())])

    if args.image:
        for img in args.image:
            cmd.extend(["-i", str(Path(img).resolve())])

    if args.output_schema:
        cmd.extend(["--output-schema", str(Path(args.output_schema).resolve())])

    if args.dangerously_bypass:
        cmd.append("--dangerously-bypass-approvals-and-sandbox")

    if args.ephemeral:
        cmd.append("--ephemeral")

    # Read prompt from stdin and output last message to dedicated file
    cmd.extend(["--json", "-o", str(last_message_file), "-"])
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Universal Headless Codex Runner with context passing, sandboxing, and telemetry.",
    )
    parser.add_argument("prompt", nargs="?", help="Task text or '-' for stdin.")
    parser.add_argument("--prompt-file", help="File containing task brief / prompt.")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Model identifier (default: {DEFAULT_MODEL}).")
    parser.add_argument(
        "-e", "--effort", default=DEFAULT_EFFORT, choices=EFFORTS,
        help=f"Reasoning effort (default: {DEFAULT_EFFORT}).",
    )
    parser.add_argument(
        "-s", "--sandbox", default=DEFAULT_SANDBOX, choices=SANDBOXES,
        help=f"Execution sandbox policy (default: {DEFAULT_SANDBOX}).",
    )
    parser.add_argument(
        "--allow-full-access", action="store_true",
        help="Explicit permission guard required if using --sandbox danger-full-access.",
    )
    parser.add_argument(
        "--dangerously-bypass", action="store_true",
        help="Bypass all sandbox and confirmation checks (use only in external sandboxes).",
    )
    parser.add_argument("-C", "--cd", "--cwd", dest="cwd", default=".", help="Working directory root.")
    parser.add_argument("--add-dir", action="append", help="Additional directories that should be writable.")
    parser.add_argument("--worktree", action="store_true", help="Execute in an isolated managed git worktree.")
    parser.add_argument("-c", "--config", action="append", help="Configuration override key=value (repeatable).")
    parser.add_argument("-i", "--image", action="append", help="Image file path to attach (repeatable).")
    parser.add_argument("--output-schema", help="Path to JSON Schema file enforcing structured output.")
    parser.add_argument("--resume", metavar="THREAD_ID", help="Resume previous interactive/headless thread.")
    parser.add_argument("--fork", metavar="THREAD_ID", help="Fork an existing session into a new thread.")
    parser.add_argument("--ephemeral", action="store_true", help="Run without persisting thread to local disk.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT}).")
    parser.add_argument("--out-dir", help="Explicit directory to save run artifacts.")
    parser.add_argument("--dry-run", action="store_true", help="Print constructed command and exit without invoking codex.")
    args = parser.parse_args()

    if args.sandbox == "danger-full-access" and not args.allow_full_access:
        fail("Using --sandbox danger-full-access requires passing --allow-full-access explicitly.")

    prompt_text = read_prompt(args)
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        fail(f"Working directory does not exist: {cwd}")

    codex_bin = shutil.which("codex")
    if not codex_bin and not args.dry_run:
        fail("The 'codex' executable was not found on PATH.")
    codex_bin = codex_bin or "codex"

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:6]}"
    run_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.gettempdir()) / "codex-headless-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = run_dir / "prompt.md"
    prompt_file.write_text(prompt_text, encoding="utf-8")
    last_msg_file = run_dir / "last_message.md"
    events_file = run_dir / "events.jsonl"
    stderr_file = run_dir / "stderr.log"
    result_file = run_dir / "result.json"

    cmd = build_command(args, codex_bin, cwd, last_msg_file)

    if args.dry_run:
        cmd_str = " ".join(f'"{c}"' if " " in c or "\n" in c else c for c in cmd)
        print(f"DRY RUN COMMAND:\n{cmd_str}\n")
        print(f"CWD: {cwd}")
        print(f"Prompt length: {len(prompt_text)} characters (saved to {prompt_file})")
        return EXIT_OK

    start_time = time.monotonic()
    timed_out = False

    with open(events_file, "wb") as ev_out, open(stderr_file, "wb") as err_out:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=ev_out,
            stderr=err_out,
            start_new_session=(os.name != "nt"),
        )
        try:
            proc.communicate(input=prompt_text.encode("utf-8"), timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_process_tree(proc)
            proc.communicate()

    duration = round(time.monotonic() - start_time, 2)
    thread_id, usage = parse_events(events_file)
    final_output = last_msg_file.read_text(encoding="utf-8") if last_msg_file.exists() else ""

    if timed_out:
        status = "timeout"
        exit_code = EXIT_TIMEOUT
    elif proc.returncode == 0 and final_output.strip():
        status = "success"
        exit_code = EXIT_OK
    else:
        status = "error"
        exit_code = proc.returncode or 1

    result_data = {
        "status": status,
        "exit_code": exit_code,
        "model": args.model,
        "effort": args.effort,
        "sandbox": None if (args.resume or args.fork) else args.sandbox,
        "cwd": str(cwd),
        "thread_id": thread_id or args.resume or args.fork,
        "resumed": bool(args.resume or args.fork),
        "duration_seconds": duration,
        "usage": usage,
        "run_dir": str(run_dir),
        "timeout_seconds": args.timeout,
    }
    result_file.write_text(json.dumps(result_data, indent=2), encoding="utf-8")

    if final_output:
        sys.stdout.write(final_output if final_output.endswith("\n") else final_output + "\n")

    if status != "success":
        err_tail = stderr_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-15:]
        if err_tail:
            print("\n--- STDERR LOG (TAIL) ---", file=sys.stderr)
            print("\n".join(err_tail), file=sys.stderr)

    print(
        f"codex_headless: status={status} model={args.model} effort={args.effort} "
        f"duration={duration}s thread={result_data['thread_id']} run_dir={run_dir}",
        file=sys.stderr,
    )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

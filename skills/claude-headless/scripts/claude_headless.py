#!/usr/bin/env python3
r"""Universal Headless Claude Runner.

Executes Claude Code non-interactively via `claude -p` (print mode),
supporting model selection (sonnet, haiku, opus), output formatting (json, text),
system prompt injection, allowed tool whitelisting, permission bypassing,
session continuation/resumption, and timeout-guaranteed process tree cleanup.

Outputs:
  stdout: Response text or JSON payload from Claude Code
  stderr: Status telemetry, duration, and error logs if failed
  exit code:
    0: Success
    124: Execution timed out (process tree cleanly terminated)
    2: Configuration or usage error
    1: Claude execution failure
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
from typing import Dict, List, Optional

DEFAULT_MODEL = "claude-3-7-sonnet"
DEFAULT_TIMEOUT = 1800  # 30 minutes
FORMATS = ("text", "json", "stream-json")

EXIT_OK = 0
EXIT_TIMEOUT = 124
EXIT_USAGE = 2
EXIT_FAILED = 1


def fail(message: str, code: int = EXIT_USAGE) -> None:
    print(f"claude_headless: ERROR: {message}", file=sys.stderr)
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


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Recursively terminate Claude process tree on timeout."""
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


def build_command(
    args: argparse.Namespace,
    claude_bin: str,
    prompt_text: str,
) -> List[str]:
    cmd = [claude_bin, "-p"]

    if args.model:
        cmd.extend(["--model", args.model])

    if args.output_format:
        cmd.extend(["--output-format", args.output_format])

    if args.dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    if args.allowed_tools:
        cmd.extend(["--allowed-tools", args.allowed_tools])

    if args.tools:
        cmd.extend(["--tools", args.tools])

    if args.system_prompt:
        cmd.extend(["--system-prompt", args.system_prompt])
    elif args.system_prompt_file:
        cmd.extend(["--system-prompt-file", str(Path(args.system_prompt_file).resolve())])

    if args.append_system_prompt:
        cmd.extend(["--append-system-prompt", args.append_system_prompt])
    elif args.append_system_prompt_file:
        cmd.extend(["--append-system-prompt-file", str(Path(args.append_system_prompt_file).resolve())])

    if args.add_dir:
        for extra in args.add_dir:
            cmd.extend(["--add-dir", str(Path(extra).resolve())])

    if args.bare:
        cmd.append("--bare")

    if args.resume:
        cmd.extend(["--resume", args.resume])
    elif args.continue_last:
        cmd.append("--continue")

    if args.json_schema:
        cmd.extend(["--json-schema", args.json_schema])

    # Pass prompt as trailing argument
    cmd.append(prompt_text)
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Universal Headless Claude Runner with context passing, tools, and telemetry.",
    )
    parser.add_argument("prompt", nargs="?", help="Task text or '-' for stdin.")
    parser.add_argument("--prompt-file", help="File containing task brief / prompt.")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Model identifier (default: {DEFAULT_MODEL}).")
    parser.add_argument(
        "--output-format", default="json", choices=FORMATS,
        help="Output format: text, json, stream-json (default: json).",
    )
    parser.add_argument(
        "--dangerously-skip-permissions", action="store_true",
        help="Bypass all permission checks for tools.",
    )
    parser.add_argument("--allowed-tools", help="Comma or space-separated list of allowed tools (e.g. 'Bash,Read,Edit').")
    parser.add_argument("--tools", help="List of available tools or 'default'.")
    parser.add_argument("--system-prompt", help="System prompt override.")
    parser.add_argument("--system-prompt-file", help="Path to system prompt file.")
    parser.add_argument("--append-system-prompt", help="Append to default system prompt.")
    parser.add_argument("--append-system-prompt-file", help="Path to file to append to system prompt.")
    parser.add_argument("-C", "--cd", "--cwd", dest="cwd", default=".", help="Working directory root.")
    parser.add_argument("--add-dir", action="append", help="Additional directories to allow tool access.")
    parser.add_argument("--bare", action="store_true", help="Minimal mode (skip hooks, LSP, auto-memory).")
    parser.add_argument("--resume", metavar="SESSION_ID", help="Resume previous session ID.")
    parser.add_argument("-c", "--continue", dest="continue_last", action="store_true", help="Continue the most recent conversation.")
    parser.add_argument("--json-schema", help="JSON schema to enforce output structure.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT}).")
    parser.add_argument("--out-dir", help="Explicit directory to save run artifacts.")
    parser.add_argument("--dry-run", action="store_true", help="Print constructed command and exit without invoking claude.")
    args = parser.parse_args()

    prompt_text = read_prompt(args)
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        fail(f"Working directory does not exist: {cwd}")

    claude_bin = shutil.which("claude")
    if not claude_bin and not args.dry_run:
        fail("The 'claude' executable was not found on PATH.")
    claude_bin = claude_bin or "claude"

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:6]}"
    run_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.gettempdir()) / "claude-headless-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = run_dir / "prompt.md"
    prompt_file.write_text(prompt_text, encoding="utf-8")
    stdout_file = run_dir / "stdout.json" if args.output_format == "json" else run_dir / "stdout.txt"
    stderr_file = run_dir / "stderr.log"
    result_file = run_dir / "result.json"

    cmd = build_command(args, claude_bin, prompt_text)

    if args.dry_run:
        cmd_str = " ".join(f'"{c}"' if " " in c or "\n" in c else c for c in cmd)
        print(f"DRY RUN COMMAND:\n{cmd_str}\n")
        print(f"CWD: {cwd}")
        print(f"Prompt length: {len(prompt_text)} characters (saved to {prompt_file})")
        return EXIT_OK

    start_time = time.monotonic()
    timed_out = False

    # Stdin is set to DEVNULL so claude -p does not block 3s waiting for piped input
    with open(stdout_file, "wb") as out_stream, open(stderr_file, "wb") as err_stream:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=out_stream,
            stderr=err_stream,
            start_new_session=(os.name != "nt"),
        )
        try:
            proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_process_tree(proc)
            proc.wait()

    duration = round(time.monotonic() - start_time, 2)
    raw_output = stdout_file.read_text(encoding="utf-8", errors="replace").strip()

    payload: Dict = {}
    response_body = raw_output
    session_id = args.resume

    if args.output_format == "json" and raw_output:
        try:
            payload = json.loads(raw_output)
            response_body = payload.get("result", payload.get("text", raw_output))
            session_id = payload.get("session_id", session_id)
        except json.JSONDecodeError:
            pass

    if timed_out:
        status = "timeout"
        exit_code = EXIT_TIMEOUT
    elif proc.returncode == 0:
        status = "success"
        exit_code = EXIT_OK
    else:
        status = "error"
        exit_code = proc.returncode or EXIT_FAILED

    resp_file = run_dir / "response.md"
    resp_file.write_text(str(response_body), encoding="utf-8")

    result_data = {
        "status": status,
        "exit_code": exit_code,
        "model": args.model,
        "output_format": args.output_format,
        "dangerously_skip_permissions": args.dangerously_skip_permissions,
        "cwd": str(cwd),
        "session_id": session_id,
        "resumed": bool(args.resume or args.continue_last),
        "duration_seconds": duration,
        "usage": payload.get("usage"),
        "run_dir": str(run_dir),
        "timeout_seconds": args.timeout,
    }
    result_file.write_text(json.dumps(result_data, indent=2), encoding="utf-8")

    if status == "success":
        sys.stdout.write(str(response_body) if str(response_body).endswith("\n") else str(response_body) + "\n")
    else:
        err_tail = stderr_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-15:]
        if err_tail:
            print("\n--- STDERR LOG (TAIL) ---", file=sys.stderr)
            print("\n".join(err_tail), file=sys.stderr)

    print(
        f"claude_headless: status={status} model={args.model} "
        f"duration={duration}s session={session_id} run_dir={run_dir}",
        file=sys.stderr,
    )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

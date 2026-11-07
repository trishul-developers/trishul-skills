#!/usr/bin/env python3
r"""Universal Headless Antigravity (AGY) Runner.

Executes Google Antigravity non-interactively via `agy -p` (print mode),
supporting model selection (gemini-3.8-flash, claude-sonnet-4-6, etc.),
reasoning effort, permission auto-approval, JSON output formatting,
structured schema enforcement, Windows command-line length thresholding,
and timeout-guaranteed process tree cleanup.

Outputs:
  stdout: Response text or JSON payload from Antigravity
  stderr: Status telemetry, duration, and error logs if failed
  exit code:
    0: Success
    124: Execution timed out (process tree cleanly terminated)
    2: Configuration or usage error
    1: Antigravity turn failure or error status
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

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_EFFORT = "medium"
DEFAULT_TIMEOUT = 1800  # 30 minutes
EFFORTS = ("low", "medium", "high", "xhigh", "max")
MODES = ("accept-edits", "auto", "plan")
FORMATS = ("text", "json", "stream-json")
MAX_INLINE_CHARS = 16000

EXIT_OK = 0
EXIT_TIMEOUT = 124
EXIT_USAGE = 2
EXIT_FAILED = 1


def fail(message: str, code: int = EXIT_USAGE) -> None:
    print(f"agy_headless: ERROR: {message}", file=sys.stderr)
    sys.exit(code)


def read_prompt(args: argparse.Namespace) -> str:
    """Read prompt from prompt file, argument, or stdin."""
    if args.prompt_file:
        p = Path(args.prompt_file)
        if not p.is_file():
            fail(f"Prompt file does not exist: {p}")
        return p.read_text(encoding="utf-8")
    if args.prompt == "-":
        return sys.stdin.read()
    if args.prompt:
        return args.prompt
    fail("No prompt provided. Specify prompt text, --prompt-file FILE, or '-' for stdin.")
    return ""


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Recursively kill agy and its spawned language servers or tool processes."""
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
    agy_bin: str,
    prompt_str: str,
    log_path: Path,
) -> List[str]:
    # In agy CLI, -p=<prompt> or --print=<prompt> passes the prompt in print mode
    cmd = [agy_bin, f"-p={prompt_str}"]

    if args.model:
        cmd.extend(["--model", args.model])

    if args.effort:
        cmd.extend(["--effort", args.effort])

    if args.mode:
        cmd.extend(["--mode", args.mode])

    if args.output_format:
        cmd.extend(["--output-format", args.output_format])

    if args.json_schema:
        schema_path = Path(args.json_schema)
        if schema_path.is_file():
            cmd.extend(["--json-schema", str(schema_path.resolve())])
        else:
            cmd.extend(["--json-schema", args.json_schema])

    if args.auto_approve:
        cmd.append("--dangerously-skip-permissions")

    if args.add_dir:
        for extra in args.add_dir:
            cmd.extend(["--add-dir", str(Path(extra).resolve())])

    if args.resume:
        cmd.extend(["--conversation", args.resume])
    elif args.continue_last:
        cmd.append("--continue")

    cmd.extend(["--log-file", str(log_path)])
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Universal Headless Antigravity (AGY) Runner with context passing, modes, and telemetry.",
    )
    parser.add_argument("prompt", nargs="?", help="Task text or '-' for stdin.")
    parser.add_argument("--prompt-file", help="File containing task brief / prompt.")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Model identifier (default: {DEFAULT_MODEL}).")
    parser.add_argument(
        "-e", "--effort", default=DEFAULT_EFFORT, choices=EFFORTS,
        help=f"Reasoning effort (default: {DEFAULT_EFFORT}).",
    )
    parser.add_argument("--mode", choices=MODES, help="Execution mode: accept-edits, auto, plan.")
    parser.add_argument(
        "--output-format", default="json", choices=FORMATS,
        help="Output format: text, json, stream-json (default: json).",
    )
    parser.add_argument("--json-schema", help="JSON schema inline string or file path to enforce output structure.")
    parser.add_argument(
        "--auto-approve", action="store_true",
        help="Auto-approve tool permissions (--dangerously-skip-permissions).",
    )
    parser.add_argument("-C", "--cd", "--cwd", dest="cwd", default=".", help="Working directory root.")
    parser.add_argument("--add-dir", action="append", help="Additional workspace directory (repeatable).")
    parser.add_argument("--resume", metavar="CONVERSATION_ID", help="Resume previous conversation by ID.")
    parser.add_argument("-c", "--continue", dest="continue_last", action="store_true", help="Continue the most recent conversation.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT}).")
    parser.add_argument("--out-dir", help="Explicit directory to save run artifacts.")
    parser.add_argument("--dry-run", action="store_true", help="Print constructed command and exit without invoking agy.")
    args = parser.parse_args()

    prompt_text = read_prompt(args)
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        fail(f"Working directory does not exist: {cwd}")

    agy_bin = shutil.which("agy")
    if not agy_bin and not args.dry_run:
        fail("The 'agy' executable was not found on PATH.")
    agy_bin = agy_bin or "agy"

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:6]}"
    run_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.gettempdir()) / "agy-headless-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = run_dir / "prompt.md"
    prompt_file.write_text(prompt_text, encoding="utf-8")
    stdout_file = run_dir / "stdout.json" if args.output_format == "json" else run_dir / "stdout.txt"
    stderr_file = run_dir / "stderr.log"
    log_file = run_dir / "agy.log"
    result_file = run_dir / "result.json"

    # Handle command-line character length bounds on Windows
    if len(prompt_text) > MAX_INLINE_CHARS:
        prompt_arg = (
            f"Please read the full instructions from the file '{prompt_file}' and execute the task described within."
        )
    else:
        prompt_arg = prompt_text

    cmd = build_command(args, agy_bin, prompt_arg, log_file)

    if args.dry_run:
        cmd_str = " ".join(f'"{c}"' if " " in c or "\n" in c else c for c in cmd)
        print(f"DRY RUN COMMAND:\n{cmd_str}\n")
        print(f"CWD: {cwd}")
        print(f"Prompt length: {len(prompt_text)} characters (saved to {prompt_file})")
        return EXIT_OK

    start_time = time.monotonic()
    timed_out = False

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
    conversation_id = args.resume

    if args.output_format == "json" and raw_output:
        try:
            payload = json.loads(raw_output)
            response_body = payload.get("response", raw_output)
            conversation_id = payload.get("conversation_id", conversation_id)
        except json.JSONDecodeError:
            pass

    agy_status = payload.get("status", "")
    if timed_out:
        status = "timeout"
        exit_code = EXIT_TIMEOUT
    elif proc.returncode == 0 and (args.output_format != "json" or agy_status == "SUCCESS" or response_body.strip()):
        status = "success"
        exit_code = EXIT_OK
    else:
        status = "error"
        exit_code = proc.returncode if proc.returncode != 0 else EXIT_FAILED

    resp_file = run_dir / "response.md"
    resp_file.write_text(str(response_body), encoding="utf-8")

    result_data = {
        "status": status,
        "agy_status": agy_status or None,
        "exit_code": exit_code,
        "model": args.model,
        "effort": args.effort,
        "mode": args.mode,
        "auto_approve": args.auto_approve,
        "cwd": str(cwd),
        "conversation_id": conversation_id,
        "resumed": bool(args.resume or args.continue_last),
        "duration_seconds": duration,
        "usage": payload.get("usage"),
        "run_dir": str(run_dir),
        "timeout_seconds": args.timeout,
    }
    result_file.write_text(json.dumps(result_data, indent=2), encoding="utf-8")

    if status == "success":
        sys.stdout.write(response_body if response_body.endswith("\n") else response_body + "\n")
    else:
        err_tail = stderr_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-15:]
        if err_tail:
            print("\n--- STDERR LOG (TAIL) ---", file=sys.stderr)
            print("\n".join(err_tail), file=sys.stderr)

    print(
        f"agy_headless: status={status} model={args.model} effort={args.effort} "
        f"duration={duration}s conversation={conversation_id} run_dir={run_dir}",
        file=sys.stderr,
    )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

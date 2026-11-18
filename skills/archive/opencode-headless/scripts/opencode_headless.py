#!/usr/bin/env python3
r"""Universal Headless OpenCode Runner.

Executes OpenCode non-interactively via `opencode run`, supporting:
  - Granular model selection across providers (`provider/model#variant`)
  - Reasoning effort / variant control (`low`, `medium`, `high`, `max`)
  - Thinking block toggling (`--thinking`)
  - Autonomous execution with permission auto-approval (`--auto`)
  - Archival mode to keep session lists clean (`--archived`)
  - Git worktree isolation (`--worktree`)
  - Session continuation and forking (`--session`, `--continue`, `--fork`)
  - Context attachment (`--file`)
  - Stdin streaming and file-based prompt briefs
  - Windows CLI argument length safety (>16k chars fallback)
  - Process tree cleanup on timeout (`taskkill /PID /T /F` on Windows)
  - Structured run telemetry and artifact generation

Outputs:
  stdout: Response text or JSON payload from OpenCode
  stderr: Status telemetry, duration, and error logs if failed
  exit code:
    0: Success
    124: Execution timed out (process tree cleanly terminated)
    2: Configuration or usage error
    1: OpenCode execution failure
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

DEFAULT_MODEL = "anthropic/claude-3-7-sonnet"
DEFAULT_EFFORT = "high"
DEFAULT_TIMEOUT = 1800  # 30 minutes
MAX_INLINE_CHARS = 16000
EFFORTS = ("low", "medium", "high", "max")
FORMATS = ("default", "json")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_TIMEOUT = 124


def fail(message: str, code: int = EXIT_USAGE) -> None:
    print(f"opencode_headless: ERROR: {message}", file=sys.stderr)
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


def find_opencode_bin() -> Optional[str]:
    """Locate the opencode binary across platform paths and environments."""
    env_bin = os.environ.get("OPENCODE_BIN")
    if env_bin and Path(env_bin).exists():
        return env_bin

    # PATH resolution (catches opencode on Linux/WSL and opencode.exe on Windows)
    bin_path = shutil.which("opencode") or shutil.which("opencode.exe")
    if bin_path:
        return bin_path

    # Standard fallback locations
    candidates = [
        # Linux / WSL
        Path.home() / ".opencode" / "bin" / "opencode",
        Path.home() / ".local" / "bin" / "opencode",
        Path("/usr/local/bin/opencode"),
        # Native Windows
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages" / "Anomaly.OpenCode_Microsoft.Winget.Source_8wekyb3d8bbwe" / "opencode.exe",
        # WSL Windows mount
        Path("/mnt/c/Users/tosum/AppData/Local/Microsoft/WinGet/Packages/Anomaly.OpenCode_Microsoft.Winget.Source_8wekyb3d8bbwe/opencode.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)

    return None


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Recursively terminate OpenCode process tree on timeout."""
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


def compose_model_string(model: Optional[str], effort: Optional[str]) -> Optional[str]:
    """Combine base model and reasoning effort into provider/model#variant format."""
    if not model and not effort:
        return None
    if not model and effort:
        return f"#{effort}"
    if not effort:
        return model

    # If model string already specifies #variant, override with explicit effort
    base_model = model.split("#")[0]
    return f"{base_model}#{effort}"


def build_command(
    args: argparse.Namespace,
    opencode_bin: str,
    prompt_text: str,
    prompt_file: Path,
) -> Tuple[List[str], bool]:
    """Construct the opencode run command line."""
    cmd = [opencode_bin, "run"]

    effective_model = compose_model_string(args.model, args.effort)
    if effective_model:
        cmd.extend(["-m", effective_model])

    if args.agent:
        cmd.extend(["--agent", args.agent])

    if args.format:
        cmd.extend(["--format", args.format])

    if args.auto:
        cmd.append("--auto")

    if args.thinking:
        cmd.append("--thinking")

    if args.archived and not args.no_archived:
        cmd.append("--archived")

    if args.standalone:
        cmd.append("--standalone")

    if args.worktree:
        if isinstance(args.worktree, str) and args.worktree.strip() and args.worktree != "True":
            cmd.extend(["--worktree", args.worktree.strip()])
        else:
            cmd.append("--worktree")

    if args.session:
        cmd.extend(["--session", args.session])
    elif args.continue_last:
        cmd.append("--continue")

    if args.fork:
        cmd.append("--fork")

    if args.title:
        cmd.extend(["--title", args.title])

    if args.file:
        for f in args.file:
            resolved_file = Path(f).resolve()
            if not resolved_file.exists():
                fail(f"Attached file does not exist: {f}")
            cmd.extend(["--file", str(resolved_file)])

    # Windows command-line limit handling
    used_fallback_file = False
    if len(prompt_text) > MAX_INLINE_CHARS:
        used_fallback_file = True
        cmd.extend(["--file", str(prompt_file.resolve())])
        msg = (
            f"Please read the full instructions from the attached prompt file '{prompt_file.name}' "
            "and execute the task described within."
        )
        cmd.append(msg)
    else:
        cmd.append(prompt_text)

    return cmd, used_fallback_file


def parse_session_from_output(raw_output: str) -> Optional[str]:
    """Attempt to extract session ID from stdout if formatted as JSON."""
    if not raw_output:
        return None
    for line in raw_output.splitlines():
        line = line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            data = json.loads(line)
            if isinstance(data, dict):
                session = data.get("session_id") or data.get("session") or data.get("id")
                if session:
                    return str(session)
        except json.JSONDecodeError:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Universal Headless OpenCode Runner with model/effort control, worktree isolation, and telemetry.",
    )
    parser.add_argument("prompt", nargs="?", help="Task text or '-' for stdin.")
    parser.add_argument("--prompt-file", help="File containing task brief / prompt.")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Model identifier in provider/model format (default: {DEFAULT_MODEL}).")
    parser.add_argument(
        "-e", "--effort", "--variant", dest="effort", default=DEFAULT_EFFORT,
        help=f"Reasoning effort / variant level (e.g. low, medium, high, max; default: {DEFAULT_EFFORT}).",
    )
    parser.add_argument(
        "--format", default="default", choices=FORMATS,
        help="Output format: default or json (default: default).",
    )
    parser.add_argument(
        "--auto", action="store_true", default=True,
        help="Auto-approve tool execution permissions not explicitly denied (default: True).",
    )
    parser.add_argument(
        "--no-auto", dest="auto", action="store_false",
        help="Disable automatic permission approval.",
    )
    parser.add_argument(
        "--thinking", action="store_true",
        help="Show model thinking blocks in output.",
    )
    parser.add_argument(
        "--archived", action="store_true", default=True,
        help="Mark session as archived to keep session lists clean (default: True).",
    )
    parser.add_argument(
        "--no-archived", dest="no_archived", action="store_true",
        help="Do not mark session as archived.",
    )
    parser.add_argument("--agent", help="Specify agent persona to use.")
    parser.add_argument("-w", "--worktree", nargs="?", const="True", help="Start session in an isolated git worktree, optionally named.")
    parser.add_argument("-f", "--file", action="append", help="File path to attach to context (repeatable).")
    parser.add_argument("-s", "--session", metavar="SESSION_ID", help="Session ID to continue or create.")
    parser.add_argument("-c", "--continue", dest="continue_last", action="store_true", help="Continue the most recent session.")
    parser.add_argument("--fork", action="store_true", help="Fork the session before continuing.")
    parser.add_argument("--title", help="Session title.")
    parser.add_argument("--standalone", action="store_true", help="Run with private server instead of background service.")
    parser.add_argument("-C", "--cd", "--cwd", dest="cwd", default=".", help="Working directory root.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT}).")
    parser.add_argument("--out-dir", help="Explicit directory to save run artifacts.")
    parser.add_argument("--dry-run", action="store_true", help="Print constructed command and exit without invoking opencode.")

    args = parser.parse_args()

    prompt_text = read_prompt(args)
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        fail(f"Working directory does not exist: {cwd}")

    opencode_bin = find_opencode_bin()
    if not opencode_bin and not args.dry_run:
        fail("The 'opencode' executable was not found on PATH or standard install locations.")
    opencode_bin = opencode_bin or "opencode"

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:6]}"
    run_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.gettempdir()) / "opencode-headless-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = run_dir / "prompt.md"
    prompt_file.write_text(prompt_text, encoding="utf-8")
    stdout_file = run_dir / "stdout.json" if args.format == "json" else run_dir / "stdout.txt"
    stderr_file = run_dir / "stderr.log"
    result_file = run_dir / "result.json"

    cmd, used_fallback = build_command(args, opencode_bin, prompt_text, prompt_file)

    if args.dry_run:
        cmd_str = " ".join(f'"{c}"' if (" " in c or "\n" in c) else c for c in cmd)
        print(f"DRY RUN COMMAND:\n{cmd_str}\n")
        print(f"CWD: {cwd}")
        print(f"Binary: {opencode_bin}")
        print(f"Prompt length: {len(prompt_text)} characters (saved to {prompt_file})")
        if used_fallback:
            print("Note: Windows CLI safety fallback active (prompt attached via --file).")
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
    session_id = args.session or parse_session_from_output(raw_output)

    if timed_out:
        status = "timed_out"
        exit_code = EXIT_TIMEOUT
    elif proc.returncode == 0:
        status = "completed"
        exit_code = EXIT_OK
    else:
        status = "failed"
        exit_code = proc.returncode

    meta = {
        "run_id": run_id,
        "status": status,
        "exit_code": exit_code,
        "duration_seconds": duration,
        "timestamp": datetime.now().isoformat(),
        "model": args.model,
        "effort": args.effort,
        "format": args.format,
        "session_id": session_id,
        "cwd": str(cwd),
        "command": cmd,
        "timed_out": timed_out,
        "artifacts": {
            "prompt": str(prompt_file),
            "stdout": str(stdout_file),
            "stderr": str(stderr_file),
            "result": str(result_file),
        },
    }
    result_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Mirror stdout to caller
    if raw_output:
        print(raw_output)

    # Status summary on stderr
    stat_msg = (
        f"opencode_headless: [{status.upper()}] exit_code={exit_code} "
        f"duration={duration}s model={args.model}#{args.effort}"
    )
    if session_id:
        stat_msg += f" session={session_id}"
    stat_msg += f" (artifacts: {run_dir})"
    print(stat_msg, file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

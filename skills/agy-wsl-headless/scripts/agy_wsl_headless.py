#!/usr/bin/env python3
r"""WSL Headless Antigravity (AGY) & Swarm Runner.

Executes Google Antigravity (`agy -p`) inside WSL (Ubuntu) from Windows or WSL,
supporting native `swarm` orchestration, Windows-to-WSL path translation,
quote-safe `bash -l -s` stdin dispatch, `--print-timeout`, and `result.json`
telemetry.

Exit codes:
  0: Success
  1: Antigravity execution failed
  2: Configuration or usage error
  124: Execution timed out
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

DEFAULT_SWARM_PRINT_TIMEOUT = "300s"
DEFAULT_SUBPROCESS_TIMEOUT = 1800
EFFORTS = ("low", "medium", "high", "xhigh", "max")
MODES = ("accept-edits", "auto", "plan")
FORMATS = ("text", "json", "stream-json")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_TIMEOUT = 124


def fail(message: str, code: int = EXIT_USAGE) -> None:
    print(f"agy_wsl_headless: ERROR: {message}", file=sys.stderr)
    sys.exit(code)


def windows_to_wsl_path(raw_path: str) -> str:
    """Convert a Windows drive path (e.g. E:\\Projects\\Foo) to /mnt/e/Projects/Foo.

    POSIX paths (starting with '/') are returned unchanged.
    """
    if raw_path.startswith("/"):
        return raw_path
    p = raw_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":" and p[0].isalpha():
        drive = p[0].lower()
        rest = p[2:]
        if not rest.startswith("/"):
            rest = "/" + rest
        return f"/mnt/{drive}{rest}"
    resolved = str(Path(raw_path).resolve()).replace("\\", "/")
    if len(resolved) >= 2 and resolved[1] == ":" and resolved[0].isalpha():
        return f"/mnt/{resolved[0].lower()}{resolved[2:]}"
    return resolved


WSL_ENV_NOTE = """## Environment note (WSL runner)

You run inside WSL on a Windows-hosted checkout under /mnt. Native WSL `git` cannot read
Windows worktrees (their gitdir paths are Windows paths) and WSL has no git-lfs or dotnet.
- Run every git command as `git.exe` (for example `git.exe status`, `git.exe add -A`, `git.exe commit`).
- If you need dotnet, use `"/mnt/c/Program Files/dotnet/dotnet.exe"`.
- ALWAYS redirect stdin of every Windows executable: `git.exe status </dev/null`, `"/mnt/c/Program Files/dotnet/dotnet.exe" --version </dev/null`. Without it they wait for stdin to close and hang your shell (minutes) when stdin is a pipe.
- Edit files in place and keep each file's existing line endings; do not reformat unrelated files.
- Do not change WSL configuration.
"""


def cwd_is_windows_mount(cwd_wsl: str) -> bool:
    return cwd_wsl.startswith("/mnt/") and len(cwd_wsl) > 5 and cwd_wsl[5].isalpha()


def read_prompt(args: argparse.Namespace) -> str:
    """Read prompt from --prompt-file, inline argument, or stdin ('-')."""
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


def build_dispatch_script(
    args: argparse.Namespace,
    prompt_file_wsl: str,
    cwd_wsl: Optional[str],
) -> str:
    """Build a quote-safe bash script streamed to `bash -l -s`."""
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f'export PATH="$HOME/.local/bin:$PATH"',
    ]
    if cwd_wsl:
        lines.append(f"cd {shlex.quote(cwd_wsl)}")

    lines.append(f"PROMPT_TEXT=$(cat {shlex.quote(prompt_file_wsl)})")

    agy_bin = shlex.quote(args.agy_bin) if args.agy_bin else "agy"
    cmd_parts: List[str] = [agy_bin, '-p="$PROMPT_TEXT"']

    if args.model:
        cmd_parts.extend(["--model", shlex.quote(args.model)])
    if args.effort:
        cmd_parts.extend(["--effort", shlex.quote(args.effort)])
    if args.mode:
        cmd_parts.extend(["--mode", shlex.quote(args.mode)])
    if args.output_format:
        cmd_parts.extend(["--output-format", shlex.quote(args.output_format)])
    if args.json_schema:
        cmd_parts.extend(["--json-schema", shlex.quote(windows_to_wsl_path(args.json_schema))])

    auto_approve = bool(args.auto_approve or args.swarm)
    if auto_approve:
        cmd_parts.append("--dangerously-skip-permissions")

    print_timeout = args.print_timeout or (DEFAULT_SWARM_PRINT_TIMEOUT if args.swarm else None)
    if print_timeout:
        cmd_parts.extend(["--print-timeout", shlex.quote(print_timeout)])

    for extra in args.add_dir or []:
        cmd_parts.extend(["--add-dir", shlex.quote(windows_to_wsl_path(extra))])

    if args.resume:
        cmd_parts.extend(["--conversation", shlex.quote(args.resume)])
    elif args.continue_last:
        cmd_parts.append("--continue")

    lines.append(" ".join(cmd_parts))
    return "\n".join(lines) + "\n"


def build_wsl_command(wsl_distro: Optional[str] = None) -> List[str]:
    """Return the outer command used to stream dispatch.sh into WSL bash."""
    if os.name == "nt":
        wsl_bin = shutil.which("wsl.exe") or shutil.which("wsl")
        if not wsl_bin:
            fail("wsl.exe not found on PATH.")
        cmd = [wsl_bin]
        if wsl_distro:
            cmd.extend(["-d", wsl_distro])
        cmd.extend(["-e", "bash", "-l", "-s"])
        return cmd
    return ["bash", "-l", "-s"]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Run Google Antigravity (`agy -p`) inside WSL with native swarm support.",
    )
    ap.add_argument("prompt", nargs="?", help="Prompt text, or '-' to read from stdin.")
    ap.add_argument("--prompt-file", help="Path to a prompt markdown/text file.")
    ap.add_argument("-m", "--model", help="Antigravity model name (optional; uses agy default if omitted).")
    ap.add_argument("-e", "--effort", choices=EFFORTS, help="Reasoning effort level.")
    ap.add_argument("--mode", choices=MODES, help="Execution mode (accept-edits, auto, plan).")
    ap.add_argument("--output-format", choices=FORMATS, help="Output format (text, json, stream-json).")
    ap.add_argument("--json-schema", help="Path to JSON schema file.")
    ap.add_argument("--auto-approve", action="store_true", help="Pass --dangerously-skip-permissions.")
    ap.add_argument(
        "--swarm",
        action="store_true",
        help="Swarm mode: implies --auto-approve and defaults --print-timeout to 300s.",
    )
    ap.add_argument(
        "--print-timeout",
        help="Duration passed to `agy --print-timeout` (e.g. 60s, 120s, 0s).",
    )
    ap.add_argument("-C", "--cd", dest="cwd", help="Working directory (Windows or WSL path).")
    ap.add_argument("--add-dir", action="append", help="Additional writable directory (repeatable).")
    ap.add_argument("--resume", metavar="CONVERSATION_ID", help="Resume an existing conversation.")
    ap.add_argument("-c", "--continue", dest="continue_last", action="store_true", help="Continue last conversation.")
    ap.add_argument("--wsl-distro", help="Optional WSL distribution name (e.g. Ubuntu).")
    ap.add_argument("--agy-bin", help="Override agy binary path inside WSL (default: agy on PATH).")
    ap.add_argument("--timeout", type=int, default=DEFAULT_SUBPROCESS_TIMEOUT, help="Outer subprocess timeout in seconds.")
    ap.add_argument("--out-dir", help="Artifact output directory.")
    ap.add_argument("--no-env-note", action="store_true", help="Do not append the WSL/git.exe environment note to the prompt.")
    ap.add_argument("--dry-run", action="store_true", help="Write dispatch.sh and print command without executing.")
    return ap.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    prompt_text = read_prompt(args)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = uuid.uuid4().hex[:6]
    out_dir = Path(args.out_dir).resolve() if args.out_dir else Path(tempfile.gettempdir()) / "agy-wsl-headless-runs" / f"{stamp}-{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = out_dir / "prompt.md"
    if not args.no_env_note and args.cwd and cwd_is_windows_mount(windows_to_wsl_path(args.cwd)):
        prompt_text = prompt_text.rstrip("\n") + "\n\n" + WSL_ENV_NOTE
    prompt_file.write_text(prompt_text, encoding="utf-8", newline="\n")

    prompt_file_wsl = windows_to_wsl_path(str(prompt_file))
    cwd_wsl = windows_to_wsl_path(args.cwd) if args.cwd else None
    dispatch_script = build_dispatch_script(args, prompt_file_wsl, cwd_wsl)
    dispatch_file = out_dir / "dispatch.sh"
    dispatch_file.write_text(dispatch_script, encoding="utf-8", newline="\n")

    outer_cmd = build_wsl_command(args.wsl_distro)

    if args.dry_run:
        print(f"OUT_DIR={out_dir}")
        print("CMD=" + " ".join(outer_cmd))
        print("--- dispatch.sh ---")
        print(dispatch_script, end="")
        return EXIT_OK

    started = time.monotonic()
    timed_out = False
    try:
        # Bytes in, bytes out: text mode would turn LF into CRLF on Windows and bash
        # would fail on `set -o pipefail`.
        proc = subprocess.run(
            outer_cmd,
            input=dispatch_script.encode("utf-8"),
            capture_output=True,
            timeout=args.timeout,
        )
        rc = proc.returncode
        stdout_text = (proc.stdout or b"").decode("utf-8", errors="replace")
        stderr_text = (proc.stderr or b"").decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        rc = EXIT_TIMEOUT
        stdout_text = (exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout) or ""
        stderr_text = (exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr) or ""

    duration = round(time.monotonic() - started, 3)
    payload: dict = {}
    response_body = stdout_text
    conversation_id = args.resume
    if args.output_format == "json" and stdout_text.strip():
        try:
            parsed = json.loads(stdout_text)
            if isinstance(parsed, dict):
                payload = parsed
                response_body = str(payload.get("response") or "")
                conversation_id = payload.get("conversation_id", conversation_id)
        except json.JSONDecodeError:
            pass
    (out_dir / "response.md").write_text(response_body, encoding="utf-8")
    (out_dir / "last_message.md").write_text(response_body, encoding="utf-8")
    (out_dir / "stdout.txt").write_text(stdout_text, encoding="utf-8")
    (out_dir / "stderr.log").write_text(stderr_text, encoding="utf-8")

    # Same rule as agy_headless.py: exit 0 and, for json output, agy_status SUCCESS or a non-empty response.
    succeeded = (not timed_out and rc == 0 and
                 (args.output_format != "json" or payload.get("status") == "SUCCESS" or bool(response_body.strip())))
    if not timed_out and rc == 0 and not succeeded:
        rc = EXIT_FAILED
    result = {
        "status": "timeout" if timed_out else ("ok" if succeeded else "failed"),
        "exit_code": rc,
        "duration_seconds": duration,
        "cwd_wsl": cwd_wsl,
        "swarm": bool(args.swarm),
        "model": args.model,
        "effort": args.effort,
        "conversation_id": conversation_id,
        "agy_status": payload.get("status"),
        "usage": payload.get("usage"),
        "print_timeout": args.print_timeout or (DEFAULT_SWARM_PRINT_TIMEOUT if args.swarm else None),
        "out_dir": str(out_dir),
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if response_body:
        print(response_body, end="" if response_body.endswith("\n") else "\n")
    if stderr_text:
        print(stderr_text, file=sys.stderr, end="" if stderr_text.endswith("\n") else "\n")

    return EXIT_OK if rc == 0 else (EXIT_TIMEOUT if timed_out else EXIT_FAILED)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
r"""Hub Wait: Self-wake waiter for Trishul Agent Hub participants.

Polls Trishul Agent Hub (GET /participants?project=<project>) until the named
participant has pending mail > 0, then prints a single notification line and exits 0.

Designed for Claude desktop chats to run in background before ending a turn:
when hub_wait exits, the desktop app wakes the same chat in-session at zero model cost.

Standard library Python 3 only.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Ensure hub_messenger can be imported from the same directory
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from hub_messenger import OSLock, query_participants, read_token  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_PROJECT = "trishul-tactical-engine"
DEFAULT_HUB_URL = "http://127.0.0.1:8765"
DEFAULT_INTERVAL = 30
DEFAULT_MAX_WAIT = 0
TEN_MINUTES_SEC = 600.0
MAX_BACKOFF_SEC = 300.0


def run_hub_wait(
    participant: str,
    project: str,
    hub_url: str,
    token_file: Path,
    interval: int = DEFAULT_INTERVAL,
    max_wait: int = DEFAULT_MAX_WAIT,
    lock_dir: Optional[Path] = None,
    time_fn: Callable[[], float] = time.time,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Core wait loop for a participant. Returns exit code."""
    if interval < 5:
        interval = 5

    if lock_dir is None:
        lock_dir = Path.home() / ".hub-messenger"
    lock_dir = Path(lock_dir)
    lock_dir.mkdir(parents=True, exist_ok=True)

    lock_file = lock_dir / f"hub_wait.{participant}.lock"
    os_lock = OSLock(lock_file)
    if not os_lock.try_acquire():
        diag = os_lock.read_diagnostics()
        pid = diag.get("pid", "unknown")
        print(f"hub_wait: already waiting for {participant} (pid {pid})")
        return 4

    payload = {
        "pid": os.getpid(),
        "participant": participant,
        "project": project,
        "start_time": time_fn(),
        "start_time_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time_fn())),
    }
    os_lock.write_diagnostics(payload)

    start_mono = monotonic_fn()
    outage_start: Optional[float] = None
    warning_printed = False
    current_interval = interval

    try:
        while True:
            now_mono = monotonic_fn()
            elapsed_total = now_mono - start_mono

            if max_wait > 0 and elapsed_total >= max_wait:
                print(f"hub_wait: no mail after {int(elapsed_total)} s. Start hub_wait again.")
                return 0

            # 1. Read token
            token: Optional[str] = None
            token_err: Optional[Exception] = None
            try:
                token = read_token(token_file)
            except Exception as e:
                token_err = e

            # 2. Fetch participants if token read succeeded
            participants: Optional[List[Dict[str, Any]]] = None
            resolved_project = project
            fetch_err: Optional[Exception] = None
            if token_err is None and token:
                participants, resolved_project, fetch_err = query_participants(
                    hub_url=hub_url,
                    project=project,
                    token=token,
                    timeout=15,
                )

            err = token_err or fetch_err
            if err is not None or participants is None:
                # Outage or network error
                if outage_start is None:
                    outage_start = now_mono

                outage_duration = now_mono - outage_start
                if outage_duration >= TEN_MINUTES_SEC and not warning_printed:
                    err_name = type(err).__name__ if err else "ConnectionError"
                    print(
                        f"hub_wait: warning: persistent hub/token failure for {int(outage_duration // 60)} minutes ({err_name}). Continuing to wait...",
                        file=sys.stderr,
                    )
                    warning_printed = True

                sleep_duration = current_interval
                if max_wait > 0:
                    remaining = max_wait - (now_mono - start_mono)
                    if remaining <= 0:
                        print(f"hub_wait: no mail after {int(now_mono - start_mono)} s. Start hub_wait again.")
                        return 0
                    sleep_duration = min(sleep_duration, remaining)
                sleep_fn(sleep_duration)
                current_interval = min(current_interval * 2, int(MAX_BACKOFF_SEC))
                continue

            # Connection succeeded; reset backoff and outage tracking
            outage_start = None
            warning_printed = False
            current_interval = interval

            # 3. Locate participant in listing (exact case-sensitive match)
            found_p = None
            for p in participants:
                if str(p.get("name", "")) == participant:
                    found_p = p
                    break

            if found_p is None:
                print(f"hub_wait: participant '{participant}' not found in project '{resolved_project}'.")
                return 3

            pending = int(found_p.get("pending", 0))
            if pending > 0:
                print(
                    f"hub_wait: {participant} has {pending} pending message(s). Read your hub inbox, then start hub_wait again."
                )
                return 0

            sleep_duration = interval
            if max_wait > 0:
                remaining = max_wait - (now_mono - start_mono)
                if remaining <= 0:
                    print(f"hub_wait: no mail after {int(now_mono - start_mono)} s. Start hub_wait again.")
                    return 0
                sleep_duration = min(sleep_duration, remaining)
            sleep_fn(sleep_duration)
    finally:
        os_lock.release()


def main():
    parser = argparse.ArgumentParser(
        description="Self-wake waiter for Trishul Agent Hub participants: waits quietly for pending mail and exits 0",
    )
    parser.add_argument(
        "--participant",
        required=True,
        help="Name of participant to wait for",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help=f"Project name (default: {DEFAULT_PROJECT})",
    )
    parser.add_argument(
        "--hub-url",
        default=DEFAULT_HUB_URL,
        help=f"Trishul Agent Hub base URL (default: {DEFAULT_HUB_URL})",
    )
    parser.add_argument(
        "--token-file",
        required=True,
        help="Path to token file containing bearer token (read into memory only; never printed or saved)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Polling interval in seconds (default: {DEFAULT_INTERVAL}, minimum: 5)",
    )
    parser.add_argument(
        "--max-wait",
        type=int,
        default=DEFAULT_MAX_WAIT,
        help="Maximum seconds to wait before exiting with re-arm (default: 0 = no limit)",
    )
    parser.add_argument(
        "--lock-dir",
        default=str(Path.home() / ".hub-messenger"),
        help="Directory for participant lock files (default: ~/.hub-messenger)",
    )

    args = parser.parse_args()

    if args.interval < 5:
        parser.error("--interval must be at least 5 seconds")

    code = run_hub_wait(
        participant=args.participant,
        project=args.project,
        hub_url=args.hub_url,
        token_file=Path(args.token_file),
        interval=args.interval,
        max_wait=args.max_wait,
        lock_dir=Path(args.lock_dir),
    )
    sys.exit(code)


if __name__ == "__main__":
    main()

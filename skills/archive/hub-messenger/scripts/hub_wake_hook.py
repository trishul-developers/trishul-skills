#!/usr/bin/env python3
r"""Hub Wake Hook: Automatic wake hook for Claude desktop chats.

Designed for Claude Code Stop (and SessionStart) hooks configured with:
  "asyncRewake": true, "timeout": 86400

Reads Claude Code hook JSON from stdin (containing session_id and hook_event_name),
maps session_id to participant and project via ~/.hub-messenger/claude_sessions.json,
and waits quietly for pending mail using hub_wait's polling engine and per-participant OS lock.

Exit code 2 wakes the Claude desktop chat with stderr resumptions.
Standard library Python 3 only.
"""

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from hub_messenger import OSLock, read_token  # noqa: E402
from hub_wait import (  # noqa: E402
    DEFAULT_HUB_URL,
    DEFAULT_INTERVAL,
    format_pending_message,
    run_hub_wait,
)

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_BASE_DIR = Path.home() / ".hub-messenger"
DEFAULT_TOKEN_FILE = Path(r"C:\Users\tosum\TrishulAgentHub\tokens\runtime.token")
DEFAULT_PROJECT = "trishul-tactical-engine"
DEFAULT_MAX_WAIT = 82800  # 23 hours
DEFAULT_REMIND_AFTER = 900.0  # 15 minutes


def close_hook_logger(log_file: Path) -> None:
    """Flush and close handlers for the logger associated with log_file."""
    logger_name = f"hub_wake_hook.{log_file.resolve()}"
    logger = logging.getLogger(logger_name)
    for h in list(logger.handlers):
        try:
            h.close()
        except Exception:
            pass
        logger.removeHandler(h)


def setup_hook_logger(log_file: Path) -> logging.Logger:
    """Configure rotating logger for hub_wake_hook: 1 MB max, 1 backup."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger_name = f"hub_wake_hook.{log_file.resolve()}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    has_handler = False
    for h in logger.handlers:
        if isinstance(h, RotatingFileHandler) and Path(h.baseFilename).resolve() == log_file.resolve():
            has_handler = True
            break

    if not has_handler:
        rfh = RotatingFileHandler(
            str(log_file),
            maxBytes=1_048_576,
            backupCount=1,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        rfh.setFormatter(formatter)
        logger.addHandler(rfh)
    return logger


def atomic_save_json(path: Path, data: Any) -> None:
    """Save data to JSON file atomically using a temporary file and replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}_{int(time.time() * 1000)}")
    try:
        temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(str(temp_path), str(path))
    except Exception:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


def load_anti_loop_state(state_file: Path) -> Dict[str, Any]:
    """Load anti-loop state from disk or return default."""
    if not state_file.exists():
        return {"last_woken_pending": 0, "last_woken_at": 0.0}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "last_woken_pending": int(data.get("last_woken_pending", 0)),
                "last_woken_at": float(data.get("last_woken_at", 0.0)),
            }
    except Exception:
        pass
    return {"last_woken_pending": 0, "last_woken_at": 0.0}


def save_anti_loop_state(state_file: Path, pending: int, woken_at: float) -> None:
    """Atomically persist anti-loop state."""
    data = {"last_woken_pending": pending, "last_woken_at": woken_at}
    atomic_save_json(state_file, data)


def reset_anti_loop_state(state_file: Path) -> None:
    """Reset anti-loop state when pending reaches 0."""
    save_anti_loop_state(state_file, 0, 0.0)


def format_max_wait_hours(elapsed_seconds: float) -> str:
    """Format elapsed seconds as hours string <h>."""
    hours = elapsed_seconds / 3600.0
    if hours >= 1.0 and hours.is_integer():
        return str(int(hours))
    elif hours >= 1.0:
        return f"{hours:.1f}".rstrip("0").rstrip(".")
    else:
        return f"{hours:.2f}".rstrip("0").rstrip(".")


def run_hook_mode(
    raw_stdin: str,
    base_dir: Optional[Path] = None,
    hub_url: str = DEFAULT_HUB_URL,
    token_file: Optional[Path] = None,
    interval: int = DEFAULT_INTERVAL,
    max_wait: int = DEFAULT_MAX_WAIT,
    remind_after: float = DEFAULT_REMIND_AFTER,
    time_fn: Callable[[], float] = time.time,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Core hook mode. Reads hook event from stdin and waits quietly for mail."""
    if not raw_stdin or not raw_stdin.strip():
        return 0

    try:
        hook_payload = json.loads(raw_stdin)
        if not isinstance(hook_payload, dict):
            return 0
    except Exception:
        return 0

    session_id = hook_payload.get("session_id")
    hook_event_name = hook_payload.get("hook_event_name", "unknown")
    if not session_id or not isinstance(session_id, str):
        return 0

    if base_dir is None:
        base_dir = DEFAULT_BASE_DIR
    base_dir = Path(base_dir).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    log_file = base_dir / "hub_wake_hook.log"
    logger = setup_hook_logger(log_file)

    sessions_file = base_dir / "claude_sessions.json"
    sessions_data: Dict[str, Any] = {}
    if sessions_file.exists():
        try:
            sessions_data = json.loads(sessions_file.read_text(encoding="utf-8"))
        except Exception:
            sessions_data = {}

    if not isinstance(sessions_data, dict) or session_id not in sessions_data:
        # Unmapped session exits 0 silently
        return 0

    mapping = sessions_data[session_id]
    if not isinstance(mapping, dict):
        return 0

    participant = mapping.get("participant")
    if not participant or not isinstance(participant, str):
        return 0

    project = mapping.get("project", DEFAULT_PROJECT)

    if token_file is None:
        if "token_file" in mapping and mapping["token_file"]:
            token_file = Path(mapping["token_file"])
        else:
            token_file = DEFAULT_TOKEN_FILE
    token_file = Path(token_file)

    logger.info(f"START event={hook_event_name} participant={participant} session={session_id[:8]}")

    state_file = base_dir / f"hub_wake_hook.{participant}.json"

    def on_lock_busy(diag: Dict[str, Any]) -> int:
        pid = diag.get("pid", "unknown")
        logger.info(f"EXIT event={hook_event_name} participant={participant} exit=0 reason=lock_already_held (pid {pid})")
        return 0

    def on_participant_missing(p_name: str, p_project: str) -> int:
        logger.warning(f"participant '{p_name}' not found in project '{p_project}'")
        logger.info(f"EXIT event={hook_event_name} participant={p_name} exit=0 reason=participant_not_found")
        return 0

    def on_pending_status(p_name: str, pending: int) -> Optional[int]:
        state = load_anti_loop_state(state_file)
        last_pending = state["last_woken_pending"]
        last_at = state["last_woken_at"]
        now = time_fn()

        if pending == 0:
            reset_anti_loop_state(state_file)
            return None

        should_wake = False
        if pending > last_pending:
            should_wake = True
        elif (now - last_at) >= remind_after:
            should_wake = True

        if should_wake:
            save_anti_loop_state(state_file, pending, now)
            msg = format_pending_message(p_name, pending)
            print(msg, file=sys.stderr)
            logger.info(f"EXIT event={hook_event_name} participant={p_name} exit=2 reason=mail_arrived pending={pending}")
            return 2

        # Anti-loop suppressed wake; keep polling silently
        return None

    def on_max_wait(p_name: str, elapsed: float) -> int:
        h_str = format_max_wait_hours(elapsed)
        msg = f"hub_wake_hook: no mail for {p_name} after {h_str} h; re-armed at end of this turn."
        print(msg, file=sys.stderr)
        logger.info(f"EXIT event={hook_event_name} participant={p_name} exit=2 reason=max_wait elapsed={int(elapsed)}")
        return 2

    def outage_logger(warning_msg: str) -> None:
        logger.warning(warning_msg)

    ret = run_hub_wait(
        participant=participant,
        project=project,
        hub_url=hub_url,
        token_file=token_file,
        interval=interval,
        max_wait=max_wait,
        lock_dir=base_dir,
        time_fn=time_fn,
        monotonic_fn=monotonic_fn,
        sleep_fn=sleep_fn,
        on_lock_busy=on_lock_busy,
        on_participant_missing=on_participant_missing,
        on_pending_status=on_pending_status,
        on_max_wait=on_max_wait,
        outage_logger=outage_logger,
    )
    close_hook_logger(log_file)
    return ret


def register_session(
    participant: str,
    project: str,
    session_id: str,
    base_dir: Path,
    token_file: Optional[str] = None,
) -> int:
    """Register participant session in claude_sessions.json atomically."""
    sessions_file = base_dir / "claude_sessions.json"
    sessions: Dict[str, Any] = {}
    if sessions_file.exists():
        try:
            sessions = json.loads(sessions_file.read_text(encoding="utf-8"))
        except Exception:
            sessions = {}

    # Remove any existing entry for the same participant and project
    to_delete = [
        sid
        for sid, entry in sessions.items()
        if isinstance(entry, dict)
        and entry.get("participant") == participant
        and entry.get("project") == project
    ]
    for sid in to_delete:
        del sessions[sid]

    # Add or update entry
    new_entry: Dict[str, Any] = {
        "participant": participant,
        "project": project,
    }
    if token_file:
        new_entry["token_file"] = str(Path(token_file).resolve())
    sessions[session_id] = new_entry

    atomic_save_json(sessions_file, sessions)
    print(f"Registered {participant} for session {session_id[:8]} (project: {project})")
    return 0


def unregister_session(
    session_id: Optional[str],
    participant: Optional[str],
    base_dir: Path,
) -> int:
    """Unregister participant session from claude_sessions.json atomically."""
    sessions_file = base_dir / "claude_sessions.json"
    if not sessions_file.exists():
        print("No registered Claude sessions.")
        return 0

    try:
        sessions = json.loads(sessions_file.read_text(encoding="utf-8"))
    except Exception:
        sessions = {}

    removed_keys = []
    if session_id:
        if session_id in sessions:
            entry = sessions.pop(session_id)
            p = entry.get("participant", "unknown") if isinstance(entry, dict) else "unknown"
            removed_keys.append((session_id, p))
    elif participant:
        to_del = [
            sid
            for sid, entry in sessions.items()
            if isinstance(entry, dict) and entry.get("participant") == participant
        ]
        for sid in to_del:
            entry = sessions.pop(sid)
            removed_keys.append((sid, participant))

    if not removed_keys:
        if session_id:
            print(f"Session {session_id[:8]} not found in registered sessions.")
        elif participant:
            print(f"Participant '{participant}' not found in registered sessions.")
        return 0

    atomic_save_json(sessions_file, sessions)
    for sid, p in removed_keys:
        print(f"Unregistered session {sid[:8]} ({p})")
    return 0


def list_sessions(base_dir: Path) -> int:
    """List all registered Claude sessions."""
    sessions_file = base_dir / "claude_sessions.json"
    if not sessions_file.exists():
        print("No registered Claude sessions.")
        return 0

    try:
        sessions = json.loads(sessions_file.read_text(encoding="utf-8"))
    except Exception:
        sessions = {}

    if not sessions:
        print("No registered Claude sessions.")
        return 0

    print(f"{'SESSION ID':<40} {'PARTICIPANT':<20} {'PROJECT':<25}")
    print("-" * 85)
    for sid, entry in sessions.items():
        if isinstance(entry, dict):
            p = str(entry.get("participant", "unknown"))
            proj = str(entry.get("project", "unknown"))
        else:
            p = "unknown"
            proj = "unknown"
        print(f"{sid:<40} {p:<20} {proj:<25}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="hub_wake_hook.py",
        description="Automatic wake hook for Claude desktop chats via Trishul Agent Hub.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Default hook mode reads hook JSON from stdin and wakes on mail or max-wait.",
    )
    # Hook mode options
    parser.add_argument(
        "--base-dir",
        default=str(DEFAULT_BASE_DIR),
        help=f"Base directory for sessions, locks, and logs (default: {DEFAULT_BASE_DIR})",
    )
    parser.add_argument(
        "--hub-url",
        default=DEFAULT_HUB_URL,
        help=f"Agent Hub URL (default: {DEFAULT_HUB_URL})",
    )
    parser.add_argument(
        "--token-file",
        default=None,
        help="Bearer token file path override (read into memory only)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Polling interval in seconds (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--max-wait",
        type=int,
        default=DEFAULT_MAX_WAIT,
        help=f"Max wait seconds before re-arm wake (default: {DEFAULT_MAX_WAIT} = 23 h)",
    )
    parser.add_argument(
        "--remind-after",
        type=float,
        default=DEFAULT_REMIND_AFTER,
        help=f"Anti-loop reminder interval in seconds (default: {DEFAULT_REMIND_AFTER} = 15 min)",
    )

    subparsers = parser.add_subparsers(dest="subcommand")

    # register subcommand
    reg_parser = subparsers.add_parser("register", help="Register a Claude chat session for automatic wake")
    reg_parser.add_argument("--participant", required=True, help="Participant name (e.g. manager, architect)")
    reg_parser.add_argument("--project", default=DEFAULT_PROJECT, help=f"Project name (default: {DEFAULT_PROJECT})")
    reg_parser.add_argument(
        "--session-id",
        default=None,
        help="Claude Code session ID (default: $CLAUDE_CODE_SESSION_ID)",
    )
    reg_parser.add_argument(
        "--token-file",
        default=None,
        help="Optional token file path for this participant",
    )
    reg_parser.add_argument(
        "--base-dir",
        default=argparse.SUPPRESS,
        help=f"Base directory (default: {DEFAULT_BASE_DIR})",
    )

    # unregister subcommand
    unreg_parser = subparsers.add_parser("unregister", help="Unregister a Claude chat session")
    unreg_parser.add_argument(
        "--session-id",
        default=None,
        help="Claude Code session ID to unregister (default: $CLAUDE_CODE_SESSION_ID)",
    )
    unreg_parser.add_argument(
        "--participant",
        default=None,
        help="Participant name to unregister",
    )
    unreg_parser.add_argument(
        "--base-dir",
        default=argparse.SUPPRESS,
        help=f"Base directory (default: {DEFAULT_BASE_DIR})",
    )

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List all registered Claude chat sessions")
    list_parser.add_argument(
        "--base-dir",
        default=argparse.SUPPRESS,
        help=f"Base directory (default: {DEFAULT_BASE_DIR})",
    )

    args = parser.parse_args(argv)

    if args.subcommand == "register":
        session_id = args.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
        if not session_id:
            print(
                "hub_wake_hook register: error: CLAUDE_CODE_SESSION_ID environment variable not set and --session-id not provided",
                file=sys.stderr,
            )
            return 2
        return register_session(
            participant=args.participant,
            project=args.project,
            session_id=session_id,
            base_dir=Path(args.base_dir).resolve(),
            token_file=args.token_file,
        )

    elif args.subcommand == "unregister":
        session_id = (args.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", "")).strip()
        participant = args.participant
        if not session_id and not participant:
            print(
                "hub_wake_hook unregister: error: specify --session-id or --participant (or set CLAUDE_CODE_SESSION_ID)",
                file=sys.stderr,
            )
            return 2
        return unregister_session(
            session_id=session_id if session_id else None,
            participant=participant,
            base_dir=Path(args.base_dir).resolve(),
        )

    elif args.subcommand == "list":
        return list_sessions(base_dir=Path(args.base_dir).resolve())

    # Default: hook mode
    raw_stdin = ""
    if not sys.stdin.isatty():
        try:
            raw_stdin = sys.stdin.read()
        except Exception:
            raw_stdin = ""

    token_path = Path(args.token_file).resolve() if args.token_file else None
    return run_hook_mode(
        raw_stdin=raw_stdin,
        base_dir=Path(args.base_dir).resolve(),
        hub_url=args.hub_url,
        token_file=token_path,
        interval=args.interval,
        max_wait=args.max_wait,
        remind_after=args.remind_after,
    )


if __name__ == "__main__":
    sys.exit(main())

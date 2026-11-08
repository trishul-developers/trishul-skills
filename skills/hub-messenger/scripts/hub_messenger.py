#!/usr/bin/env python3
r"""Hub Messenger: No-model messenger daemon for Trishul Tactical Engine.

Polls Trishul Agent Hub (GET /participants?project=<project>) every N seconds
and wakes idle participants with unread mail. Operates at zero model cost.

Wake rule (hub role messenger v3):
- Participant has pending > 0
- Participant is not waiting (waiting == False)
- Pending count rose since last wake, or >= 30 minutes have elapsed since last wake
- Manager is NEVER woken under any circumstances
- Wake message: "Check your hub inbox."

Standard library Python 3 only.
"""

import argparse
import atexit
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_HUB_URL = "http://127.0.0.1:8765"
DEFAULT_PROJECT = "tte"
DEFAULT_INTERVAL = 60
DEFAULT_WAKE_TIMEOUT = 900
WAKE_TEXT = "Check your hub inbox."
THIRTY_MINUTES_SEC = 1800.0


def get_default_base_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "hub-messenger"
    return Path.home() / ".hub-messenger"


def setup_logger(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("hub-messenger")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Avoid duplicate handlers on reload
    if not logger.handlers:
        # Rotating file handler: 1 MB max, 3 backups
        rfh = RotatingFileHandler(
            str(log_file),
            maxBytes=1_048_576,
            backupCount=3,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        rfh.setFormatter(formatter)
        logger.addHandler(rfh)

        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


def read_token(token_file: Path) -> str:
    """Read token file into memory only.

    Never print, log, echo, pass on a command line, or write it anywhere.
    Error messages name the path, never the contents.
    """
    if not token_file.exists():
        raise FileNotFoundError(f"Token file '{token_file}' does not exist.")
    try:
        content = token_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        raise RuntimeError(f"Failed to read token file '{token_file}': {type(e).__name__}")
    if not content:
        raise ValueError(f"Token file '{token_file}' is empty.")
    return content


def validate_target_config(target_name: str, target_cfg: Any) -> Tuple[bool, Optional[str]]:
    """Validate target configuration schema and types."""
    if not isinstance(target_cfg, dict):
        return False, f"Target '{target_name}' config must be a JSON object, got {type(target_cfg).__name__}"

    mode = target_cfg.get("mode", "log")
    if not isinstance(mode, str):
        return False, f"Target '{target_name}' mode must be a string, got {type(mode).__name__}"

    timeout = target_cfg.get("timeout")
    if timeout is not None:
        if isinstance(timeout, int):
            if timeout <= 0:
                return False, f"Target '{target_name}' timeout must be a positive integer, got {timeout}"
        elif isinstance(timeout, str) and timeout.isdigit():
            if int(timeout) <= 0:
                return False, f"Target '{target_name}' timeout must be a positive integer, got {timeout}"
        else:
            return False, f"Target '{target_name}' timeout must be an integer, got {type(timeout).__name__}"

    return True, None


def load_config(config_file: Path) -> Dict[str, Any]:
    if not config_file.exists():
        return {"targets": {}}
    try:
        content = config_file.read_text(encoding="utf-8")
        data = json.loads(content)
        return data if isinstance(data, dict) else {"targets": {}}
    except Exception:
        return {"targets": {}}


def load_state(state_file: Path) -> Dict[str, Any]:
    if not state_file.exists():
        return {"participants": {}}
    try:
        content = state_file.read_text(encoding="utf-8")
        data = json.loads(content)
        return data if isinstance(data, dict) else {"participants": {}}
    except Exception:
        return {"participants": {}}


def save_state(state_file: Path, state_data: Dict[str, Any]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_file.with_name(f"{state_file.name}.tmp.{os.getpid()}")
    try:
        tmp_path.write_text(json.dumps(state_data, indent=2), encoding="utf-8")
        tmp_path.replace(state_file)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def is_manager(participant: Dict[str, Any]) -> bool:
    name = str(participant.get("name", "")).lower()
    role = str(participant.get("role", "")).lower()
    address = str(participant.get("address", "")).lower()
    return name == "manager" or role == "project-manager" or address.endswith("/manager")


def should_wake_participant(
    participant: Dict[str, Any],
    p_state: Dict[str, Any],
    now_ts: float,
) -> Tuple[bool, str]:
    if is_manager(participant):
        return False, "Manager is never woken"

    pending = int(participant.get("pending", 0))
    if pending <= 0:
        return False, "No pending mail"

    waiting = bool(participant.get("waiting", False))
    if waiting:
        return False, "Participant is actively waiting in inbox_wait"

    last_pending = int(p_state.get("last_pending", 0))
    last_wake_ts = float(p_state.get("last_wake_ts", 0.0))

    if pending > last_pending:
        return True, f"Pending mail rose from {last_pending} to {pending}"

    time_since_wake = now_ts - last_wake_ts
    if last_wake_ts > 0 and time_since_wake >= THIRTY_MINUTES_SEC:
        minutes = int(time_since_wake // 60)
        return True, f"30m elapsed since last wake ({minutes}m ago, pending: {pending})"

    if last_wake_ts == 0.0:
        return True, f"Initial wake for idle participant with {pending} pending mail"

    return False, f"Pending unchanged ({pending}) and only {int((now_ts - last_wake_ts)//60)}m elapsed"


class OSLock:
    """Cross-platform OS-level advisory file lock held on an open handle for process lifetime.

    Windows: msvcrt.locking(fd, LK_NBLCK, 1)
    POSIX:   fcntl.flock(fd, LOCK_EX | LOCK_NB)

    When the holding process terminates (normal exit, crash, SIGKILL, or OS shutdown),
    the OS automatically closes the handle and releases the lock. No stale PID checks
    or file renames are needed.
    """

    def __init__(self, lock_path: Path):
        self.lock_path = Path(lock_path)
        self.fd: Optional[int] = None
        self.acquired: bool = False

    def try_acquire(self) -> bool:
        if self.acquired:
            return True
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o666)
        except OSError:
            return False

        try:
            if sys.platform == "win32":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError, OSError):
            os.close(fd)
            return False

        self.fd = fd
        self.acquired = True
        return True

    def write_diagnostics(self, payload: Dict[str, Any]) -> None:
        """Write diagnostics JSON for human readers. Lock state is determined solely by the OS lock."""
        if not self.acquired or self.fd is None:
            return
        try:
            prefix = b" " if sys.platform == "win32" else b""
            data = prefix + (json.dumps(payload, indent=2) + "\n").encode("utf-8")
            os.lseek(self.fd, 0, os.SEEK_SET)
            os.ftruncate(self.fd, 0)
            os.write(self.fd, data)
            if hasattr(os, "fsync"):
                os.fsync(self.fd)
        except Exception:
            pass

    def read_diagnostics(self) -> Dict[str, Any]:
        """Read diagnostics from lock file for reporting. Never used to decide lock ownership."""
        try:
            if not self.lock_path.exists():
                return {}
            try:
                content = self.lock_path.read_text(encoding="utf-8", errors="replace")
            except PermissionError:
                # On Windows, byte 0 is locked by msvcrt.locking; read starting at byte 1
                with open(self.lock_path, "rb") as f:
                    f.seek(1)
                    content = f.read().decode("utf-8", errors="replace")
            if content.strip():
                parsed = json.loads(content.strip())
                if isinstance(parsed, dict):
                    return parsed
        except Exception:
            pass
        return {}

    def release(self) -> None:
        if not self.acquired or self.fd is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                try:
                    os.lseek(self.fd, 0, os.SEEK_SET)
                    msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
                except Exception:
                    pass
            os.close(self.fd)
        except Exception:
            pass
        finally:
            self.fd = None
            self.acquired = False


class MessengerPidLock:
    """Single-instance guard using OS-level file locking."""

    def __init__(self, pid_file: Path):
        self.pid_file = Path(pid_file)
        self._os_lock = OSLock(self.pid_file)
        self.acquired = False
        self._registered_handlers = False

    def acquire(self) -> None:
        if self._os_lock.try_acquire():
            self.acquired = True
            self._install_handlers()
            payload = {
                "pid": os.getpid(),
                "start_time": time.time(),
                "start_time_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            }
            self._os_lock.write_diagnostics(payload)
            return

        diag = self._os_lock.read_diagnostics()
        locked_pid = diag.get("pid", "unknown")
        raise RuntimeError(
            f"Another hub-messenger instance is already running (PID {locked_pid}). Exiting."
        )

    def release(self) -> None:
        if self.acquired:
            self._os_lock.release()
            self.acquired = False

    def _install_handlers(self) -> None:
        if self._registered_handlers:
            return
        self._registered_handlers = True
        atexit.register(self.release)

        def _signal_handler(signum, frame):
            self.release()
            sys.exit(128 + signum if isinstance(signum, int) else 1)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _signal_handler)
            except (ValueError, AttributeError):
                pass


class HubMessenger:
    def __init__(
        self,
        hub_url: str,
        project: str,
        token_file: Optional[Path],
        config_path: Path,
        state_path: Path,
        log_path: Path,
        interval: int = DEFAULT_INTERVAL,
        dry_run: bool = False,
    ):
        self.hub_url = hub_url.rstrip("/")
        self.project = project
        self.resolved_project = project
        self.token_file = token_file
        self.config_path = config_path
        self.state_path = state_path
        self.log_path = log_path
        self.interval = interval
        self.dry_run = dry_run
        self.logger = setup_logger(log_path)
        self.pid_lock = MessengerPidLock(self.state_path.with_suffix(".pid"))

        # Active wake subprocesses: target_name -> (proc, start_ts, timeout)
        self.active_wakes: Dict[str, Tuple[subprocess.Popen, float, int]] = {}

        # Outage and error tracking
        self.hub_down = False
        self.backoff_delay = interval
        self.token_error_logged = False
        self.auth_failed = False

    def fetch_participants(self) -> Optional[List[Dict[str, Any]]]:
        token = ""
        if self.token_file:
            try:
                token = read_token(self.token_file)
                if self.token_error_logged:
                    self.logger.info(f"Token file '{self.token_file}' is now accessible. Resuming...")
                    self.token_error_logged = False
            except Exception:
                if not self.token_error_logged:
                    self.logger.error(
                        f"Cannot read token file '{self.token_file}'. Backing off..."
                    )
                    self.token_error_logged = True
                self.hub_down = True
                return None

        headers = {
            "Accept": "application/json",
            "User-Agent": "Hub-Messenger/1.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Endpoints to try: /v1/participants (mounted prefix in app.py) then /participants
        path_candidates = ["/v1/participants", "/participants"]
        projects_to_try = [self.resolved_project]
        if self.resolved_project == "tte":
            projects_to_try.append("trishul-tactical-engine")
        elif self.resolved_project == "trishul-tactical-engine":
            projects_to_try.append("tte")

        last_error = None
        for path_prefix in path_candidates:
            for proj in projects_to_try:
                url = f"{self.hub_url}{path_prefix}?project={urllib.parse.quote(proj)}"
                req = urllib.request.Request(url, headers=headers, method="GET")
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        if isinstance(data, list):
                            if proj != self.resolved_project:
                                self.logger.info(f"Resolved project '{self.resolved_project}' to '{proj}'")
                                self.resolved_project = proj
                            if self.auth_failed:
                                self.auth_failed = False
                            return data
                except urllib.error.HTTPError as e:
                    last_error = e
                    if e.code == 404:
                        continue
                    if e.code == 401:
                        if not self.auth_failed:
                            self.logger.error(
                                f"Authentication failed (HTTP 401) using token file '{self.token_file}'. Backing off..."
                            )
                            self.auth_failed = True
                        self.hub_down = True
                        return None
                except Exception as e:
                    last_error = e

        if last_error:
            if not self.hub_down:
                self.logger.error(
                    f"Hub connection failed at {self.hub_url}: {type(last_error).__name__}. Backing off..."
                )
                self.hub_down = True
            return None

        return None

    def poll_active_wakes(self) -> None:
        now = time.monotonic()
        finished = []
        for target, (proc, start_ts, timeout) in self.active_wakes.items():
            ret = proc.poll()
            if ret is not None:
                self.logger.info(f"Wake process for '{target}' finished with exit code {ret}.")
                finished.append(target)
            elif now - start_ts > timeout:
                self.logger.warning(
                    f"Wake process for '{target}' timed out after {timeout}s (PID {proc.pid}). Terminating turn in progress."
                )
                try:
                    proc.terminate()
                except Exception:
                    pass
                finished.append(target)

        for target in finished:
            del self.active_wakes[target]

    def launch_wake(self, target_name: str, target_cfg: Dict[str, Any]) -> None:
        valid, err = validate_target_config(target_name, target_cfg)
        if not valid:
            self.logger.error(f"Invalid configuration for target '{target_name}': {err}")
            return

        mode = str(target_cfg.get("mode", "log")).lower()
        if self.dry_run:
            mode = "log"

        # Default timeout: 900 s only for claude mode (which executes the turn synchronously to completion);
        # 60 s for codex mode and command (since codex queue returns quickly once queued)
        default_timeout = DEFAULT_WAKE_TIMEOUT if mode == "claude" else 60
        timeout = int(target_cfg.get("timeout", default_timeout))

        if mode == "log":
            self.logger.info(f"[LOG] Would wake participant '{target_name}': '{WAKE_TEXT}'")
            return

        # Check if wake already running for target
        if target_name in self.active_wakes:
            proc, _, _ = self.active_wakes[target_name]
            self.logger.info(
                f"Skipping wake for '{target_name}': previous wake process is still active (PID {proc.pid})."
            )
            return

        cmd: List[str] = []
        if mode == "codex":
            thread_id = target_cfg.get("thread_id")
            if not thread_id:
                self.logger.error(f"Cannot wake '{target_name}' via codex: 'thread_id' missing from config.")
                return
            thread_id_str = str(thread_id).strip()
            if thread_id_str.startswith("-"):
                self.logger.error(f"Cannot wake '{target_name}' via codex: 'thread_id' cannot start with '-'.")
                return
            codex_bin = shutil.which("codex") or "codex"
            cmd = [codex_bin, "queue", "--thread", thread_id_str, "--resume", "--message", WAKE_TEXT]

        elif mode == "claude":
            session_id = target_cfg.get("session_id")
            if not session_id:
                self.logger.error(f"Cannot wake '{target_name}' via claude: 'session_id' missing from config.")
                return
            session_id_str = str(session_id).strip()
            if session_id_str.startswith("-"):
                self.logger.error(f"Cannot wake '{target_name}' via claude: 'session_id' cannot start with '-'.")
                return
            claude_bin = shutil.which("claude") or "claude"
            cmd = [claude_bin, "-p", "--resume", session_id_str, WAKE_TEXT]

        elif mode == "command":
            raw_cmd = target_cfg.get("command")
            if isinstance(raw_cmd, list) and raw_cmd:
                cmd = [str(x) for x in raw_cmd]
            elif isinstance(raw_cmd, str) and raw_cmd:
                cmd = raw_cmd.split()
            else:
                self.logger.error(f"Cannot wake '{target_name}' via command: 'command' list missing from config.")
                return
        else:
            self.logger.warning(f"Unknown wake mode '{mode}' for target '{target_name}'. Defaulting to log.")
            self.logger.info(f"[LOG] Would wake participant '{target_name}': '{WAKE_TEXT}'")
            return

        # Never log the wake command line (thread and session IDs are handles). Log mode and target name only.
        self.logger.info(f"Launching detached wake for '{target_name}' [mode={mode}]")
        try:
            # Launch non-blocking detached process with stdin=DEVNULL
            kwargs: Dict[str, Any] = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = (
                    subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                )
            proc = subprocess.Popen(cmd, **kwargs)
            self.active_wakes[target_name] = (proc, time.monotonic(), timeout)
            self.logger.info(f"Wake process started for '{target_name}' (PID {proc.pid}).")
        except Exception as e:
            self.logger.error(f"Failed to launch wake process for '{target_name}': {e}")

    def run_poll_cycle(self) -> int:
        self.poll_active_wakes()

        participants = self.fetch_participants()
        if participants is None:
            if self.hub_down:
                self.backoff_delay = min(self.backoff_delay * 2, 300)
                return int(self.backoff_delay)
            return self.interval

        # If hub was down and came back
        if self.hub_down:
            self.logger.info(f"Hub is back online at {self.hub_url}. Resuming normal polling.")
            self.hub_down = False
            self.backoff_delay = self.interval

        config = load_config(self.config_path)
        targets_config = config.get("targets", {})

        state = load_state(self.state_path)
        p_states = state.setdefault("participants", {})

        now_ts = time.time()
        now_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
        state_modified = False

        for p in participants:
            name = p.get("name", "unknown")
            p_state = p_states.setdefault(name, {
                "last_pending": 0,
                "last_wake_ts": 0.0,
                "last_wake_iso": None,
            })

            should_wake, reason = should_wake_participant(p, p_state, now_ts)
            curr_pending = int(p.get("pending", 0))

            if should_wake:
                self.logger.info(f"Triggering wake for '{name}': {reason}")
                target_cfg = targets_config.get(name, {"mode": "log"})
                self.launch_wake(name, target_cfg)

                p_state["last_pending"] = curr_pending
                p_state["last_wake_ts"] = now_ts
                p_state["last_wake_iso"] = now_iso
                state_modified = True
            else:
                # Update pending count if changed without wake
                if curr_pending != p_state.get("last_pending"):
                    p_state["last_pending"] = curr_pending
                    state_modified = True

        if state_modified or not self.state_path.exists():
            save_state(self.state_path, state)

        return self.interval

    def start(self, once: bool = False) -> None:
        self.pid_lock.acquire()
        try:
            self.logger.info(
                f"Hub Messenger started. Target hub: {self.hub_url} | Project: {self.project} | Dry-run: {self.dry_run}"
            )
            if once:
                self.run_poll_cycle()
                self.logger.info("Single poll cycle complete (--once). Exiting.")
                return

            while True:
                sleep_duration = self.run_poll_cycle()
                time.sleep(sleep_duration)
        finally:
            self.pid_lock.release()


def main():
    base_dir = get_default_base_dir()

    parser = argparse.ArgumentParser(
        description="Zero-model Trishul Agent Hub messenger daemon: polls participants and wakes idle workers with unread mail",
    )
    parser.add_argument(
        "--hub-url",
        default=DEFAULT_HUB_URL,
        help=f"Agent Hub URL (default: {DEFAULT_HUB_URL})",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help=f"Project name to poll participants for (default: {DEFAULT_PROJECT})",
    )
    parser.add_argument(
        "--token-file",
        help="Path to token file containing bearer token (read into memory only; never printed or saved)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Polling interval in seconds (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        default=str(base_dir / "config.json"),
        help="Path to wake targets configuration file (default: %%LOCALAPPDATA%%\\hub-messenger\\config.json)",
    )
    parser.add_argument(
        "--state-file",
        dest="state_path",
        default=str(base_dir / "state.json"),
        help="Path to participant wake state persistence file (default: %%LOCALAPPDATA%%\\hub-messenger\\state.json)",
    )
    parser.add_argument(
        "--log-file",
        dest="log_path",
        default=str(base_dir / "hub-messenger.log"),
        help="Path to log file (default: %%LOCALAPPDATA%%\\hub-messenger\\hub-messenger.log)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one polling cycle and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run: forces every wake target to 'log' mode (prints/logs wake actions without spawning CLIs)",
    )

    args = parser.parse_args()

    token_path = Path(args.token_file) if args.token_file else None
    config_path = Path(args.config_path)
    state_path = Path(args.state_path)
    log_path = Path(args.log_path)

    messenger = HubMessenger(
        hub_url=args.hub_url,
        project=args.project,
        token_file=token_path,
        config_path=config_path,
        state_path=state_path,
        log_path=log_path,
        interval=args.interval,
        dry_run=args.dry_run,
    )
    try:
        messenger.start(once=args.once)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

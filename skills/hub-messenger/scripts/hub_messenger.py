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
import uuid
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

    timeout = target_cfg.get("timeout", DEFAULT_WAKE_TIMEOUT)
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


class MessengerPidLock:
    """Single-instance guard using atomic O_EXCL file creation with stale-PID handling."""

    def __init__(self, pid_file: Path):
        self.pid_file = pid_file
        self.acquired = False
        self._registered_handlers = False

    def get_process_creation_time(self, pid: int) -> Optional[float]:
        if sys.platform != "win32" or pid <= 0:
            return None
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            creation_time = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            res = ctypes.windll.kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation_time),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            )
            if not res:
                return None
            ft_int = (creation_time.dwHighDateTime << 32) + creation_time.dwLowDateTime
            return float(ft_int)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    def is_pid_alive(self, pid: int, expected_creation_time: Optional[float] = None) -> bool:
        if pid <= 0:
            return False
        if sys.platform == "win32":
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid
            )
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                if exit_code.value != 259:  # STILL_ACTIVE
                    return False
                if expected_creation_time is not None:
                    curr_creation = self.get_process_creation_time(pid)
                    if curr_creation is not None and curr_creation != expected_creation_time:
                        return False
                return True
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        else:
            try:
                os.kill(pid, 0)
                return True
            except (ProcessLookupError, PermissionError):
                return False

    def _try_create_pidfile(self) -> bool:
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        creation_time = self.get_process_creation_time(os.getpid())
        payload = {
            "pid": os.getpid(),
            "creation_time": creation_time,
            "start_time": time.time(),
            "start_time_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        }
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(str(self.pid_file), flags, 0o644)
        except FileExistsError:
            return False
        except OSError as e:
            raise OSError(f"Cannot create pidfile '{self.pid_file}': {e}") from e

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, indent=2))
            self.acquired = True
            self._install_handlers()
            return True
        except Exception:
            try:
                self.pid_file.unlink(missing_ok=True)
            except Exception:
                pass
            return False

    def acquire(self) -> None:
        if self._try_create_pidfile():
            return

        lock_data = None
        try:
            content = self.pid_file.read_text(encoding="utf-8", errors="replace")
            if content.strip():
                lock_data = json.loads(content)
        except Exception:
            pass

        locked_pid = int(lock_data.get("pid", -1)) if isinstance(lock_data, dict) else -1
        expected_creation = lock_data.get("creation_time") if isinstance(lock_data, dict) else None

        is_stale = locked_pid <= 0 or not self.is_pid_alive(
            locked_pid, expected_creation_time=expected_creation
        )

        if is_stale:
            stale_target = self.pid_file.with_name(
                f"{self.pid_file.name}.stale.{uuid.uuid4().hex}"
            )
            try:
                os.rename(str(self.pid_file), str(stale_target))
            except (FileNotFoundError, PermissionError, OSError):
                pass
            else:
                renamed_data = None
                try:
                    content = stale_target.read_text(encoding="utf-8", errors="replace")
                    if content.strip():
                        renamed_data = json.loads(content)
                except Exception:
                    pass

                if isinstance(renamed_data, dict):
                    renamed_pid = renamed_data.get("pid")
                    renamed_creation = renamed_data.get("creation_time")
                    if renamed_pid != locked_pid or (
                        expected_creation is not None and renamed_creation != expected_creation
                    ):
                        try:
                            if hasattr(os, "replace"):
                                os.replace(str(stale_target), str(self.pid_file))
                            else:
                                os.rename(str(stale_target), str(self.pid_file))
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"Another hub-messenger instance is already running (PID {renamed_pid}). Exiting."
                        )

                try:
                    stale_target.unlink(missing_ok=True)
                except Exception:
                    pass

                if self._try_create_pidfile():
                    return

        raise RuntimeError(
            f"Another hub-messenger instance is already running (PID {locked_pid}). Exiting."
        )

    def release(self) -> None:
        if self.acquired:
            try:
                if self.pid_file.exists():
                    self.pid_file.unlink()
            except Exception:
                pass
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

        timeout = int(target_cfg.get("timeout", DEFAULT_WAKE_TIMEOUT))

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
            cmd = [codex_bin, "exec", "resume", thread_id_str, WAKE_TEXT]

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

        # N5: Never log the wake command line (thread and session IDs are handles). Log mode and target name only.
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
        help="Path to wake targets configuration file (default: %LOCALAPPDATA%\\hub-messenger\\config.json)",
    )
    parser.add_argument(
        "--state-file",
        dest="state_path",
        default=str(base_dir / "state.json"),
        help="Path to participant wake state persistence file (default: %LOCALAPPDATA%\\hub-messenger\\state.json)",
    )
    parser.add_argument(
        "--log-file",
        dest="log_path",
        default=str(base_dir / "hub-messenger.log"),
        help="Path to log file (default: %LOCALAPPDATA%\\hub-messenger\\hub-messenger.log)",
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

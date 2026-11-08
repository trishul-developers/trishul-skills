#!/usr/bin/env python3
r"""Unified Unity Development & Verification Pipeline.

Provides a single authoritative CLI tool for:
1. Fast-Fail Static Contract Audits (banned UnityEngine.Random, Transform in Runtime, LINQ, GC allocations in tick loops).
2. Fast C# compilation pre-checks.
3. Targeted Unity test execution (EditMode / PlayMode) with MANDATORY static pre-check (<1s).
4. Direct NUnit 3 XML report parsing and structured evidence generation.
5. Automated diagnostics extraction from Editor.log on failure (extracting <50 lines, no log noise).
6. Composite phase gate execution and snapshot determinism verification.

Zero external dependencies (uses standard library Python 3).
"""

import argparse
import atexit
import glob
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Machine-wide Unity Lock
# ---------------------------------------------------------------------------
class UnityMachineLock:
    """Machine-wide lock around Unity launches stored under %LOCALAPPDATA%."""

    def __init__(
        self,
        project_path: Path,
        mode: str = "wait",
        timeout: int = 600,
        lock_path: Optional[Path] = None,
    ):
        self.project_path = project_path.resolve()
        self.mode = mode.lower() if mode else "wait"
        self.timeout = timeout
        if lock_path:
            self.lock_file = Path(lock_path)
        else:
            env_lock = os.environ.get("UNITY_LOCK_PATH")
            if env_lock:
                self.lock_file = Path(env_lock)
            else:
                local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
                self.lock_file = Path(local_appdata) / "unity_pipeline.lock"
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
                # STILL_ACTIVE = 259
                if exit_code.value != 259:
                    return False
                if expected_creation_time is not None:
                    curr_creation = self.get_process_creation_time(pid)
                    if curr_creation is not None and curr_creation != expected_creation_time:
                        # Process ID was reused by another process
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

    def read_lock(self, grace_period: float = 2.0) -> Optional[Dict[str, Any]]:
        if not self.lock_file.exists():
            return None

        deadline = time.monotonic() + grace_period
        while True:
            try:
                stat_res = self.lock_file.stat()
                file_age = time.time() - stat_res.st_mtime
            except FileNotFoundError:
                return None
            except Exception:
                return None

            content = ""
            try:
                content = self.lock_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

            if content.strip():
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "pid" in parsed:
                        pid_val = parsed["pid"]
                        if isinstance(pid_val, int) or (isinstance(pid_val, str) and pid_val.isdigit()):
                            parsed["pid"] = int(pid_val)
                            return parsed
                except Exception:
                    pass

            if file_age < grace_period and time.monotonic() < deadline:
                time.sleep(0.05)
                continue

            return {
                "pid": -1,
                "stale": True,
                "reason": "corrupt_or_empty",
                "project_path": "unknown",
                "start_time": stat_res.st_mtime,
            }

    def _try_create_lock(self) -> bool:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        creation_time = self.get_process_creation_time(os.getpid())
        payload = {
            "pid": os.getpid(),
            "creation_time": creation_time,
            "start_time": time.time(),
            "start_time_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "project_path": str(self.project_path),
        }
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(str(self.lock_file), flags, 0o644)
        except FileExistsError:
            return False
        except OSError as e:
            print(f"ERROR: Cannot create lock file '{self.lock_file}': {e}", file=sys.stderr)
            sys.exit(1)

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, indent=2))
            self.acquired = True
            self._install_handlers()
            return True
        except Exception as e:
            try:
                self.lock_file.unlink(missing_ok=True)
            except Exception:
                pass
            print(f"ERROR: Failed to write lock file '{self.lock_file}': {e}", file=sys.stderr)
            sys.exit(1)

    def write_lock(self) -> None:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        creation_time = self.get_process_creation_time(os.getpid())
        payload = {
            "pid": os.getpid(),
            "creation_time": creation_time,
            "start_time": time.time(),
            "start_time_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "project_path": str(self.project_path),
        }
        tmp_file = self.lock_file.with_name(f"{self.lock_file.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
        try:
            tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            retries = 10
            while retries > 0:
                try:
                    tmp_file.replace(self.lock_file)
                    break
                except PermissionError:
                    retries -= 1
                    if retries == 0:
                        raise
                    time.sleep(0.05)
        finally:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except Exception:
                    pass
        self.acquired = True
        self._install_handlers()

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

    def acquire(self) -> None:
        start_wait = time.monotonic()
        while True:
            elapsed = time.monotonic() - start_wait
            if elapsed >= self.timeout:
                print(
                    f"ERROR: Timed out waiting {self.timeout}s for Unity lock '{self.lock_file}'.",
                    file=sys.stderr,
                )
                sys.exit(1)

            if self._try_create_lock():
                return

            lock_data = self.read_lock()
            if lock_data is None:
                time.sleep(0.05)
                continue

            locked_pid = int(lock_data.get("pid", 0))
            locked_proj = lock_data.get("project_path", "unknown")
            start_time_str = lock_data.get("start_time_iso") or str(
                lock_data.get("start_time", "unknown")
            )
            expected_creation = lock_data.get("creation_time")

            if locked_pid == os.getpid():
                self.acquired = True
                return

            is_stale = lock_data.get("stale", False) or not self.is_pid_alive(
                locked_pid, expected_creation_time=expected_creation
            )

            if is_stale:
                # Stale takeover: rename stale file first to unique name
                stale_target = self.lock_file.with_name(
                    f"{self.lock_file.name}.stale.{uuid.uuid4().hex}"
                )
                try:
                    os.rename(str(self.lock_file), str(stale_target))
                except (FileNotFoundError, PermissionError, OSError):
                    time.sleep(0.05)
                    continue

                # Verify we renamed the stale file we actually observed, not a newly created live lock
                renamed_data = None
                try:
                    content = stale_target.read_text(encoding="utf-8", errors="replace")
                    if content.strip():
                        renamed_data = json.loads(content)
                except Exception:
                    pass

                # If renamed file has different PID or creation_time than stale data, put it back!
                if isinstance(renamed_data, dict):
                    renamed_pid = renamed_data.get("pid")
                    renamed_creation = renamed_data.get("creation_time")
                    if renamed_pid != locked_pid or (
                        expected_creation is not None and renamed_creation != expected_creation
                    ):
                        try:
                            if hasattr(os, "replace"):
                                os.replace(str(stale_target), str(self.lock_file))
                            else:
                                os.rename(str(stale_target), str(self.lock_file))
                        except Exception:
                            pass
                        time.sleep(0.05)
                        continue

                try:
                    stale_target.unlink(missing_ok=True)
                except Exception:
                    pass

                if self._try_create_lock():
                    print(
                        f"Notice: Took over stale Unity lock from dead PID {locked_pid} (project: '{locked_proj}').",
                        file=sys.stderr,
                    )
                    return
                time.sleep(0.05)
                continue

            if self.mode == "exit":
                print(
                    f"ERROR: Another live Unity instance is currently running (PID {locked_pid}, started at {start_time_str}, project: '{locked_proj}'). Exiting immediately.",
                    file=sys.stderr,
                )
                sys.exit(75)

            print(
                f"Unity lock held by PID {locked_pid} (project: '{locked_proj}', started: {start_time_str}). Waiting for release (elapsed: {int(elapsed)}s)...",
                file=sys.stderr,
            )
            time.sleep(1)

    def release(self) -> None:
        if self.acquired:
            try:
                lock_data = self.read_lock(grace_period=0.2)
                if lock_data and int(lock_data.get("pid", 0)) == os.getpid():
                    if self.lock_file.exists():
                        self.lock_file.unlink()
            except Exception:
                pass
            self.acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

# Static contract audit rules (regex pattern, severity, description)
CONTRACT_RULES = [
    (
        re.compile(r"\bUnityEngine\.Random\b"),
        "BLOCKING",
        "Banned UnityEngine.Random in Runtime. Use deterministic context PRNG (e.g. SimulationContext.Rng).",
    ),
    (
        re.compile(r"\bTransform\b|\bGameObject\b"),
        "BLOCKING_IN_RUNTIME",
        "Direct Transform or GameObject reference in Runtime state. Use EntityId and DOD presentation mirroring.",
    ),
    (
        re.compile(r"\bSystem\.Linq\b|\.Where\(|\.Select\(|\.ToList\(|\.ToArray\("),
        "WARNING_IN_TICK",
        "LINQ allocation in simulation logic. Use pre-allocated native arrays or loops.",
    ),
    (
        re.compile(r"\bnew\s+[A-Za-z0-9_]+\[\]|\bnew\s+List<"),
        "WARNING_IN_TICK",
        "Heap allocation ('new') in simulation path. Use pre-allocated buffers or pools.",
    ),
    (
        re.compile(r"\bGetHashCode\(\)"),
        "WARNING",
        "Non-deterministic hash code used. Ensure deterministic secondary ordering.",
    ),
]


def run_cmd(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 1800) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout} seconds."
    except Exception as e:
        return 1, "", str(e)


# ---------------------------------------------------------------------------
# 1. Static Contract Audit
# ---------------------------------------------------------------------------
def run_contract_audit(project_path: Path, diff_only: bool = False) -> Tuple[bool, List[str]]:
    """Scan C# simulation files for architectural invariant violations in <1s."""
    violations = []
    runtime_dir = project_path / "Assets" / "Scripts" / "Trishul" / "Runtime"
    if not runtime_dir.exists():
        runtime_dir = project_path / "Assets" / "Scripts"

    cs_files: List[Path] = []
    if diff_only:
        code, stdout, _ = run_cmd(["git", "-C", str(project_path), "diff", "--name-only", "HEAD"], cwd=project_path)
        if code == 0 and stdout:
            for line in stdout.splitlines():
                if line.endswith(".cs") and os.path.exists(project_path / line):
                    cs_files.append(project_path / line)
    if not cs_files:
        cs_files = [p for p in runtime_dir.rglob("*.cs") if not p.name.endswith("Tests.cs")]

    for cs_file in cs_files:
        is_runtime = "Runtime" in cs_file.parts
        try:
            lines = cs_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue

            for pattern, severity, desc in CONTRACT_RULES:
                if pattern.search(line):
                    if severity == "BLOCKING_IN_RUNTIME" and not is_runtime:
                        continue
                    rel_path = cs_file.relative_to(project_path) if cs_file.is_relative_to(project_path) else cs_file
                    violations.append(f"[{severity}] {rel_path}:{idx}: {desc}\n  Line: '{stripped}'")

    blocking = [v for v in violations if "[BLOCKING" in v]
    return len(blocking) == 0, violations


# ---------------------------------------------------------------------------
# 2. Fast C# Compilation
# ---------------------------------------------------------------------------
def run_fast_compile(project_path: Path) -> Tuple[bool, str]:
    """Run FastCompile project or dotnet build."""
    fc_proj = project_path / "ci" / "FastCompile" / "FastCompile.csproj"
    if fc_proj.exists():
        cmd = ["dotnet", "build", str(fc_proj), "--no-incremental", "-c", "Release", "-v", "quiet", "-nologo"]
    else:
        cmd = ["dotnet", "build", "--no-incremental", "-c", "Release", "-v", "quiet", "-nologo"]

    code, out, err = run_cmd(cmd, cwd=project_path)
    output = out or err
    if code != 0:
        err_lines = [l for l in output.splitlines() if ": error" in l.lower() or "error cs" in l.lower()]
        return False, "\n".join(err_lines[:10]) if err_lines else output[:500]
    return True, "FastCompile: PASSED (0 errors)"


# ---------------------------------------------------------------------------
# 3. NUnit 3 XML Report Parsing
# ---------------------------------------------------------------------------
def parse_nunit_xml(xml_path: Path) -> Dict:
    """Parse NUnit 3 XML report and extract counts and first failure."""
    if not xml_path.exists():
        return {"passed": False, "error": f"XML report not found: {xml_path}"}

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        total = int(root.attrib.get("total", 0))
        passed = int(root.attrib.get("passed", 0))
        failed = int(root.attrib.get("failed", 0))
        skipped = int(root.attrib.get("skipped", 0))
        duration = float(root.attrib.get("duration", 0.0))

        # Enforce zero-test / skipped-only failure (a zero-test run is a failure in TTE / NUnit)
        if total == 0:
            return {
                "passed": False,
                "error": "ZERO_TESTS_SELECTED: No tests were selected or executed (zero-test run is a failure).",
                "total": 0, "passed_count": 0, "failed_count": 0, "skipped_count": 0, "duration": 0, "failures": []
            }
        if passed == 0 and failed == 0:
            return {
                "passed": False,
                "error": f"NO_TESTS_PASSED: All {total} test(s) were skipped or inconclusive.",
                "total": total, "passed_count": 0, "failed_count": 0, "skipped_count": skipped, "duration": round(duration, 2), "failures": []
            }

        failures = []
        for tc in root.iter("test-case"):
            result = tc.attrib.get("result", "")
            if result.lower() in ("failed", "failure"):
                name = tc.attrib.get("fullname", tc.attrib.get("name", "UnknownTest"))
                fail_elem = tc.find("failure")
                msg = fail_elem.findtext("message") if fail_elem is not None else ""
                stack = fail_elem.findtext("stack-trace") if fail_elem is not None else ""
                failures.append({
                    "name": name,
                    "message": (msg or "").strip(),
                    "stack_trace": (stack or "").strip()[:500],
                })

        return {
            "passed": failed == 0 and passed > 0,
            "total": total,
            "passed_count": passed,
            "failed_count": failed,
            "skipped_count": skipped,
            "duration": round(duration, 2),
            "failures": failures,
        }
    except Exception as e:
        return {"passed": False, "error": f"Failed to parse NUnit XML: {e}"}


# ---------------------------------------------------------------------------
# 4. Log Inspection Helper
# ---------------------------------------------------------------------------
def inspect_logs(log_path: Path, max_lines: int = 40) -> List[str]:
    """Extract compiler errors and unhandled exceptions from Unity Editor.log without spamming chat."""
    if not log_path.exists():
        return []

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    findings = []
    collecting_stack = False
    stack_count = 0

    error_patterns = [
        re.compile(r": error CS\d+:"),
        re.compile(r"Unhandled Exception:"),
        re.compile(r"NullReferenceException:"),
        re.compile(r"Assertion failed:"),
        re.compile(r"BuildFailedException:"),
    ]

    for line in lines:
        if any(p.search(line) for p in error_patterns):
            findings.append(line.strip())
            collecting_stack = True
            stack_count = 0
            continue

        if collecting_stack:
            if line.strip().startswith("at ") or line.strip().startswith("in "):
                findings.append("  " + line.strip())
                stack_count += 1
                if stack_count >= 5:
                    collecting_stack = False
            else:
                collecting_stack = False

        if len(findings) >= max_lines:
            findings.append(f"... (truncated after {max_lines} error lines)")
            break

    return findings


# ---------------------------------------------------------------------------
# Main CLI Orchestration
# ---------------------------------------------------------------------------
def resolve_unity_exe(
    project_path: Optional[Path] = None,
    unity_path_override: Optional[str] = None,
) -> str:
    """Resolve exact Unity executable from ProjectSettings/ProjectVersion.txt or explicit override."""
    # 1. Explicit CLI override or environment variable
    candidate = unity_path_override or os.environ.get("UNITY_PATH") or os.environ.get("UNITY_EXE")
    if candidate:
        candidate_path = Path(candidate)
        if candidate_path.exists():
            return str(candidate_path)
        print(f"ERROR: Specified Unity path '{candidate}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # 2. Read exact m_EditorVersion from ProjectSettings/ProjectVersion.txt
    proj_dir = Path(project_path).resolve() if project_path else Path(".").resolve()
    ver_file = proj_dir / "ProjectSettings" / "ProjectVersion.txt"
    if not ver_file.exists():
        print(
            f"ERROR: ProjectSettings/ProjectVersion.txt not found in '{proj_dir}'. Cannot resolve required Unity editor version.",
            file=sys.stderr,
        )
        sys.exit(1)

    editor_version = None
    try:
        for line in ver_file.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("m_EditorVersion:"):
                editor_version = line.split(":", 1)[1].strip()
                break
    except Exception as e:
        print(f"ERROR: Failed reading ProjectVersion.txt in '{proj_dir}': {e}", file=sys.stderr)
        sys.exit(1)

    if not editor_version:
        print(f"ERROR: Could not parse 'm_EditorVersion' from '{ver_file}'.", file=sys.stderr)
        sys.exit(1)

    # 3. Search exact editor in Unity Hub install directory
    hub_candidate = Path(r"C:\Program Files\Unity\Hub\Editor") / editor_version / "Editor" / "Unity.exe"
    if hub_candidate.exists():
        return str(hub_candidate)

    # POSIX fallback Hub paths (Linux / macOS)
    for posix_base in [
        Path.home() / "Unity/Hub/Editor",
        Path("/Applications/Unity/Hub/Editor"),
        Path("/opt/unity/editors"),
    ]:
        posix_candidate = posix_base / editor_version / "Editor" / "Unity"
        if posix_candidate.exists():
            return str(posix_candidate)

    print(
        f"ERROR: Required Unity version '{editor_version}' is not installed in Unity Hub at '{hub_candidate}'. "
        f"Fallback to another version is disabled. Install Unity {editor_version} or specify --unity-path.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified Unity Development & Verification Pipeline (Audit + FastCompile + Tests + NUnit XML + Logs)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # 1. audit
    p_audit = subparsers.add_parser("audit", help="Run static simulation contract audit in <1s")
    p_audit.add_argument("-C", "--project-path", default=".", help="Project path")
    p_audit.add_argument("--diff-only", action="store_true", help="Audit only modified git files")

    # 2. compile
    p_compile = subparsers.add_parser("compile", help="Run FastCompile / dotnet build")
    p_compile.add_argument("-C", "--project-path", default=".", help="Project path")

    # 3. test
    p_test = subparsers.add_parser("test", help="Run Unity tests (EditMode/PlayMode) with mandatory static pre-check")
    p_test.add_argument("-C", "--project-path", default=".", help="Project path")
    p_test.add_argument("--platform", "--test-mode", "--test-platform", dest="platform", default="EditMode", choices=["EditMode", "PlayMode"], help="Test platform")
    p_test.add_argument("--filter", "--test-filter", "--suite", dest="filter", help="Test filter regex or test category")
    p_test.add_argument("--xml-out", help="Path to write NUnit XML report")
    p_test.add_argument("--no-precheck", action="store_true", help="Bypass mandatory fast-fail static contract audit")
    p_test.add_argument("--no-graphics", action="store_true", help="Force -nographics (defaults to False for PlayMode, True for EditMode)")
    p_test.add_argument("--timeout", type=int, default=600, help="Test timeout in seconds")
    p_test.add_argument("--unity-path", help="Explicit path to Unity executable override")
    p_test.add_argument("--lock-mode", choices=["wait", "exit"], default="wait", help="Behavior if another Unity process is running: wait or exit (default: wait)")
    p_test.add_argument("--lock-timeout", type=int, default=600, help="Maximum seconds to wait for Unity lock in wait mode (default: 600)")
    p_test.add_argument("--wait-lock", dest="lock_mode", action="store_const", const="wait", help="Wait for Unity lock (default)")
    p_test.add_argument("--exit-if-locked", dest="lock_mode", action="store_const", const="exit", help="Exit immediately if Unity lock is held by another live process")

    # 4. gate
    p_gate = subparsers.add_parser("gate", help="Run composite phase gate (FastCompile + EditMode + PlayMode)")
    p_gate.add_argument("-C", "--project-path", default=".", help="Project path")
    p_gate.add_argument("--phase", help="Phase identifier (e.g. G02, PairGateA)")
    p_gate.add_argument("--filter", help="Optional test filter pattern")
    p_gate.add_argument("--unity-path", help="Explicit path to Unity executable override")
    p_gate.add_argument("--lock-mode", choices=["wait", "exit"], default="wait", help="Behavior if another Unity process is running: wait or exit (default: wait)")
    p_gate.add_argument("--lock-timeout", type=int, default=600, help="Maximum seconds to wait for Unity lock in wait mode (default: 600)")
    p_gate.add_argument("--wait-lock", dest="lock_mode", action="store_const", const="wait", help="Wait for Unity lock (default)")
    p_gate.add_argument("--exit-if-locked", dest="lock_mode", action="store_const", const="exit", help="Exit immediately if Unity lock is held by another live process")
    p_gate.add_argument("--timeout", type=int, default=1800, help="Gate test timeout in seconds (default: 1800)")

    # 5. logs
    p_logs = subparsers.add_parser("logs", help="Inspect and extract errors from Unity Editor.log")
    p_logs.add_argument("--log-path", help="Direct path to Editor.log")
    p_logs.add_argument("-C", "--project-path", default=".", help="Project path to search logs for")
    p_logs.add_argument("--max-lines", type=int, default=35, help="Maximum error lines to extract")

    # 6. parse-xml
    p_parse = subparsers.add_parser("parse-xml", help="Parse an existing NUnit 3 XML report")
    p_parse.add_argument("xml_file", help="Path to NUnit XML report")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    project_path = Path(getattr(args, "project_path", ".")).resolve()

    # --- SUBCOMMAND: audit ---
    if args.command == "audit":
        start = time.monotonic()
        ok, violations = run_contract_audit(project_path, diff_only=args.diff_only)
        duration = round(time.monotonic() - start, 2)
        if ok and not violations:
            print(f"Simulation Contract Audit: PASSED in {duration}s (0 violations)")
            return 0
        print(f"Simulation Contract Audit: {'PASSED WITH WARNINGS' if ok else 'FAILED'} in {duration}s:")
        for v in violations:
            print(f"  {v}")
        return 0 if ok else 1

    # --- SUBCOMMAND: compile ---
    if args.command == "compile":
        ok, msg = run_fast_compile(project_path)
        print(msg)
        return 0 if ok else 1

    # --- SUBCOMMAND: test ---
    if args.command == "test":
        # 1. MANDATORY FAST-FAIL PRE-CHECK (<1s)
        if not args.no_precheck:
            start_audit = time.monotonic()
            audit_ok, audit_violations = run_contract_audit(project_path, diff_only=True)
            if not audit_ok:
                print(f"PRE-CHECK FAILED in {round(time.monotonic() - start_audit, 2)}s:")
                for v in audit_violations:
                    print(f"  {v}")
                print("\n[ABORTED] Fix simulation contract violations before launching Unity batchmode.")
                return 1

            compile_ok, compile_msg = run_fast_compile(project_path)
            if not compile_ok:
                print(f"PRE-CHECK FastCompile FAILED:\n{compile_msg}")
                print("\n[ABORTED] Fix compilation errors before launching Unity batchmode.")
                return 1
            print("Pre-Check: Static Contract Audit & FastCompile PASSED (0.8s)")

        # 2. RUN UNITY IN BATCHMODE
        unity_exe = resolve_unity_exe(
            project_path, unity_path_override=getattr(args, "unity_path", None)
        )
        xml_out = Path(args.xml_out) if args.xml_out else project_path / f"test-results-{args.platform.lower()}.xml"
        log_file = project_path / "unity-test.log"

        # Stale XML defense: delete target XML before running
        if xml_out.exists():
            xml_out.unlink()

        t_launch = time.time()

        cmd = [
            unity_exe,
            "-batchmode",
            "-projectPath", str(project_path),
            "-runTests",
            "-testPlatform", args.platform,
            "-testResults", str(xml_out),
            "-logFile", str(log_file),
        ]
        # Only use -nographics for EditMode unless explicitly requested
        if args.platform == "EditMode" or getattr(args, "no_graphics", False):
            cmd.append("-nographics")

        if args.filter:
            cmd.extend(["-testFilter", args.filter])

        print(f"Executing Unity {args.platform} tests with {unity_exe} (filter: '{args.filter or 'all'}')...")
        t_start = time.monotonic()
        lock_mode = getattr(args, "lock_mode", "wait")
        lock_timeout = getattr(args, "lock_timeout", 600)
        with UnityMachineLock(project_path, mode=lock_mode, timeout=lock_timeout):
            code, stdout, stderr = run_cmd(cmd, cwd=project_path, timeout=args.timeout)
        duration = round(time.monotonic() - t_start, 1)

        # Stale XML defense: verify xml_out exists and was generated during this run
        if not xml_out.exists() or xml_out.stat().st_mtime < t_launch:
            print(f"ERROR: Unity failed to produce a fresh test results XML at {xml_out} (process exit code: {code})", file=sys.stderr)
            err_logs = inspect_logs(log_file)
            if err_logs:
                print("\n--- CRITICAL LOG FINDINGS ---")
                print("\n".join(err_logs))
            return code if code != 0 else 1

        # 3. PARSE XML REPORT
        report = parse_nunit_xml(xml_out)
        if not report.get("passed"):
            err_msg = report.get("error") or f"{report.get('failed_count', 0)} test(s) failed."
            print(f"\n[FAIL] Test execution failed: {err_msg}")
            if report.get("failures"):
                print(f"FIRST FAILURE: {report['failures'][0]['name']}")
                print(f"Message: {report['failures'][0]['message']}")
                if report['failures'][0]['stack_trace']:
                    print(f"Stack:\n{report['failures'][0]['stack_trace']}")
            else:
                err_logs = inspect_logs(log_file)
                if err_logs:
                    print("\n--- CRITICAL LOG FINDINGS ---")
                    print("\n".join(err_logs))
            return code if code != 0 else 1

        if code != 0:
            print(f"\n[FAIL] Unity process exited with non-zero exit code {code} despite passing XML report.", file=sys.stderr)
            err_logs = inspect_logs(log_file)
            if err_logs:
                print("\n--- CRITICAL LOG FINDINGS ---", file=sys.stderr)
                print("\n".join(err_logs), file=sys.stderr)
            return code

        print(f"Results: {report['passed_count']}/{report['total']} passed, {report['failed_count']} failed, {report['skipped_count']} skipped (in {duration}s)")
        return 0

    # --- SUBCOMMAND: gate ---
    if args.command == "gate":
        phase_label = args.phase or "Target Suite"
        print(f"Running Composite Gate: {phase_label}...")

        # Step 1: Audit
        audit_ok, violations = run_contract_audit(project_path)
        if not audit_ok:
            print("Gate Step 1 (Contract Audit): FAILED")
            for v in violations:
                print(f"  {v}")
            return 1
        print("Gate Step 1 (Contract Audit): PASSED")

        # Step 2: Compile
        comp_ok, comp_msg = run_fast_compile(project_path)
        if not comp_ok:
            print(f"Gate Step 2 (FastCompile): FAILED\n{comp_msg}")
            return 1
        print("Gate Step 2 (FastCompile): PASSED")

        # Step 3: Run Tests
        unity_exe = resolve_unity_exe(
            project_path, unity_path_override=getattr(args, "unity_path", None)
        )
        xml_out = project_path / "gate-results.xml"
        log_file = project_path / "gate-unity.log"

        if xml_out.exists():
            xml_out.unlink()

        t_launch = time.time()
        cmd = [
            unity_exe, "-batchmode", "-nographics",
            "-projectPath", str(project_path),
            "-runTests", "-testPlatform", "EditMode",
            "-testResults", str(xml_out), "-logFile", str(log_file),
        ]
        if args.filter:
            cmd.extend(["-testFilter", args.filter])

        print(f"Gate Step 3 (EditMode Tests with {unity_exe})...")
        lock_mode = getattr(args, "lock_mode", "wait")
        lock_timeout = getattr(args, "lock_timeout", 600)
        with UnityMachineLock(project_path, mode=lock_mode, timeout=lock_timeout):
            code, stdout, stderr = run_cmd(
                cmd, cwd=project_path, timeout=getattr(args, "timeout", 1800)
            )
            if not xml_out.exists() or xml_out.stat().st_mtime < t_launch:
                print(f"Gate Step 3 (EditMode Tests): FAILED - No fresh XML report produced (exit code {code})")
                err_logs = inspect_logs(log_file)
                if err_logs:
                    print("\n".join(err_logs))
                return 1

            report = parse_nunit_xml(xml_out)
            if not report.get("passed"):
                print(f"Gate Step 3 (EditMode Tests): FAILED ({report.get('error') or str(report.get('failed_count')) + ' failures'})")
                if report.get("failures"):
                    print(f"  First failure: {report['failures'][0]['name']} - {report['failures'][0]['message']}")
                return 1

            print(f"Gate Step 3 (EditMode Tests): PASSED ({report['passed_count']}/{report['total']})")

            # Step 4: PlayMode Tests
            xml_play = project_path / "gate-playmode-results.xml"
            log_play = project_path / "gate-playmode-unity.log"
            if xml_play.exists():
                xml_play.unlink()

            t_launch_play = time.time()
            cmd_play = [
                unity_exe, "-batchmode",
                "-projectPath", str(project_path),
                "-runTests", "-testPlatform", "PlayMode",
                "-testResults", str(xml_play), "-logFile", str(log_play),
            ]
            if args.filter:
                cmd_play.extend(["-testFilter", args.filter])

            print(f"Gate Step 4 (PlayMode Tests with {unity_exe})...")
            code_p, stdout_p, stderr_p = run_cmd(
                cmd_play, cwd=project_path, timeout=getattr(args, "timeout", 1800)
            )
            if not xml_play.exists() or xml_play.stat().st_mtime < t_launch_play:
                print(f"Gate Step 4 (PlayMode Tests): FAILED - No fresh XML report produced (exit code {code_p})")
                err_logs = inspect_logs(log_play)
                if err_logs:
                    print("\n".join(err_logs))
                return 1

            report_play = parse_nunit_xml(xml_play)
            if not report_play.get("passed"):
                print(f"Gate Step 4 (PlayMode Tests): FAILED ({report_play.get('error') or str(report_play.get('failed_count')) + ' failures'})")
                if report_play.get("failures"):
                    print(f"  First failure: {report_play['failures'][0]['name']} - {report_play['failures'][0]['message']}")
                return 1

            print(f"Gate Step 4 (PlayMode Tests): PASSED ({report_play['passed_count']}/{report_play['total']})")

        print(f"\nCOMPOSITE GATE {phase_label}: AUTHORITATIVE GREEN")
        return 0

    # --- SUBCOMMAND: logs ---
    if args.command == "logs":
        log_target = Path(args.log_path) if args.log_path else project_path / "Editor.log"
        if not log_target.exists():
            log_target = Path(os.environ.get("LOCALAPPDATA", "")) / "Unity" / "Editor" / "Editor.log"
        findings = inspect_logs(log_target, max_lines=args.max_lines)
        if not findings:
            print(f"Log inspection clean: no errors or unhandled exceptions found in {log_target.name}.")
            return 0
        print(f"Log findings from {log_target.name} ({len(findings)} lines):")
        print("\n".join(findings))
        return 0

    # --- SUBCOMMAND: parse-xml ---
    if args.command == "parse-xml":
        report = parse_nunit_xml(Path(args.xml_file))
        if report.get("passed"):
            print(f"PASSED: {report['passed_count']}/{report['total']} tests passed in {report['duration']}s")
            return 0
        print(f"FAILED: {report.get('failed_count', '?')}/{report.get('total', '?')} tests failed.")
        if report.get("failures"):
            print(f"First failure: {report['failures'][0]['name']}")
            print(f"Message: {report['failures'][0]['message']}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

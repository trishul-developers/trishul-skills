#!/usr/bin/env python3
r"""
Unity Log Inspector & Diagnostics Tool.
Ukrainian Warfare Project.

Intelligently parses Unity Editor logs (Editor.log, Editor-prev.log, upm.log):
- Suppresses thousands of lines of boilerplate noise (licensing, memory configs, asset remapping)
- Extracts C# compilation errors & warnings (CS\d+)
- Extracts Burst compiler diagnostics (BC\d+)
- Extracts unhandled exceptions, assertion failures, and stack traces
- Isolates test runner completion status and exit codes
"""

import argparse
import glob
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


NOISE_PATTERNS = [
    re.compile(r"^\[Licensing::"),
    re.compile(r"^\[UnityMemory\]"),
    re.compile(r"memorysetup-temp-allocator-size-"),
    re.compile(r"^MonoPathRemapper: Attempts to remap"),
    re.compile(r"^Import(ed|ing) 'GUID:"),
    re.compile(r"^Failed to collect Windows signature"),
    re.compile(r"^d3d12: failed to query info queue"),
    re.compile(r"^abort_threads: Failed aborting"),
    re.compile(r"^\[INFO\s*\]\s*\[relay\]"),
    re.compile(r"^Lingering sessions upon destruction"),
    re.compile(r"^Unity Data Store service was"),
    re.compile(r"^UDS shutting down"),
    re.compile(r"^Shut down UDS"),
    re.compile(r"^AcceleratorClientConnectionCallback"),
    re.compile(r"^Cleanup mono"),
    re.compile(r"^CodeReloadManager destroyed"),
    re.compile(r"^debugger-agent: Unable to listen"),
    re.compile(r"^Checking for leaked weakptr:"),
    re.compile(r"^Found no leaked weakptrs"),
    re.compile(r"^\[Package Manager\] Server process was shutdown"),
    re.compile(r"^##utp:\{"),
    re.compile(r"^Unloading \d+ Unused Serialized files"),
    re.compile(r"^Unloading \d+ unused Assets"),
    re.compile(r"^Memory consumption went from"),
    re.compile(r"^Total: \d+\.\d+ ms \(FindLiveObjects:"),
    re.compile(r"^Asset Pipeline Refresh"),
    re.compile(r"^\[Physics::Module\]"),
    re.compile(r"^Input System module state changed"),
    re.compile(r"^Input Polling Thread exited"),
]

COMPILATION_PATTERN = re.compile(r"(?:error|warning)\s+(CS\d+|BC\d+):", re.IGNORECASE)
EXCEPTION_PATTERN = re.compile(r"\b(Exception|NullReferenceException|IndexOutOfRangeException|Assertion failed|Fatal error)\b", re.IGNORECASE)
TEST_EXIT_PATTERN = re.compile(r"Test run completed\.\s+Exiting with code\s+(\d+)\s*\((.*?)\)", re.IGNORECASE)
COMMAND_LINE_PATTERN = re.compile(r"COMMAND LINE ARGUMENTS:")


def is_noise(line):
    for pat in NOISE_PATTERNS:
        if pat.search(line):
            return True
    return False


def resolve_log_file(project_root, custom_file=None):
    if custom_file:
        if os.path.exists(custom_file):
            return os.path.abspath(custom_file)
        print(f"ERROR: Specified log file not found: {custom_file}", file=sys.stderr)
        sys.exit(1)

    candidates = [
        os.path.join(project_root, "Logs", "Editor.log"),
        os.path.join(project_root, "Logs", "Editor-prev.log"),
        os.path.expandvars(r"%LOCALAPPDATA%\Unity\Editor\Editor.log"),
    ]

    for c in candidates:
        if os.path.exists(c) and os.path.getsize(c) > 0:
            return os.path.abspath(c)

    # Return first existing even if 0 size
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)

    print("ERROR: No Unity editor log file could be located.", file=sys.stderr)
    sys.exit(1)


def list_logs(project_root):
    patterns = [
        os.path.join(project_root, "Logs", "*.log"),
        os.path.join(project_root, "Logs", "*.txt"),
        os.path.expandvars(r"%LOCALAPPDATA%\Unity\Editor\*.log"),
    ]
    files = []
    for p in patterns:
        files.extend(glob.glob(p))

    print("=======================================================")
    print("              DISCOVERED UNITY LOG FILES               ")
    print("=======================================================")
    for f in sorted(set(files)):
        size_kb = os.path.getsize(f) / 1024.0
        mtime = os.path.getmtime(f)
        import time
        t_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
        print(f"{t_str} | {size_kb:8.1f} KB | {f}")
    print("-------------------------------------------------------")


def inspect_log(log_path, mode="summary", tail_count=50):
    if not os.path.exists(log_path):
        print(f"ERROR: File not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    compilation_issues = []
    exceptions = []
    test_exits = []
    clean_lines = []

    recording_cmd = False
    cmd_lines = []

    for idx, line in enumerate(lines, 1):
        s_line = line.strip()

        if COMMAND_LINE_PATTERN.search(s_line):
            recording_cmd = True
            cmd_lines = []
            continue

        if recording_cmd:
            if s_line.startswith("Successfully changed project path") or s_line.startswith("[UnityMemory]"):
                recording_cmd = False
            else:
                if s_line:
                    cmd_lines.append(s_line)

        # Check for compilation errors
        if COMPILATION_PATTERN.search(s_line):
            compilation_issues.append((idx, s_line))

        # Check for exceptions
        if EXCEPTION_PATTERN.search(s_line) and not is_noise(s_line):
            # Capture up to 3 following lines for stack trace context
            stack_context = [s_line]
            for forward in range(1, 4):
                if idx - 1 + forward < len(lines):
                    next_s = lines[idx - 1 + forward].strip()
                    if next_s and not is_noise(next_s):
                        stack_context.append(next_s)
            exceptions.append((idx, stack_context))

        # Check for test exit status
        t_match = TEST_EXIT_PATTERN.search(s_line)
        if t_match:
            test_exits.append((idx, s_line, t_match.group(1), t_match.group(2)))

        if not is_noise(s_line) and s_line:
            clean_lines.append((idx, s_line))

    # Output formatting
    print("=======================================================")
    print("              UNITY LOG DIAGNOSTICS REPORT             ")
    print("=======================================================")
    print(f"Log File      : {log_path}")
    print(f"Total Lines   : {len(lines)}")
    print(f"Filtered Lines: {len(clean_lines)} (Noise suppressed: {len(lines) - len(clean_lines)})")

    if cmd_lines:
        print("\nLast Invocation Command Line:")
        for c in cmd_lines:
            print(f"  {c}")

    if test_exits:
        print("\nTest Runner Completion Status:")
        for idx, full, code, status in test_exits:
            print(f"  [Line {idx}] Exit Code {code} ({status})")

    if compilation_issues:
        print(f"\nCompilation Diagnostics ({len(compilation_issues)}):")
        for idx, text in compilation_issues:
            print(f"  [Line {idx}] {text}")
    elif mode == "compilation":
        print("\nCompilation Diagnostics: 0 compilation errors or warnings found.")

    if exceptions:
        print(f"\nExceptions & Assertions ({len(exceptions)}):")
        for idx, ctx in exceptions:
            print(f"\n  [Line {idx}] {ctx[0]}")
            for extra in ctx[1:]:
                print(f"    {extra}")
    elif mode == "errors":
        print("\nExceptions & Assertions: None found.")

    if mode == "summary" or mode == "tail":
        print(f"\nRecent Meaningful Events (Last {min(tail_count, len(clean_lines))} lines):")
        print("-------------------------------------------------------")
        for idx, text in clean_lines[-tail_count:]:
            print(f"[{idx:4d}] {text}")

    print("\n-------------------------------------------------------")
    has_errors = (len(compilation_issues) > 0) or (len(exceptions) > 0) or any(code != "0" for _, _, code, _ in test_exits)
    print(f"DIAGNOSTIC_VERDICT: {'ACTION_REQUIRED' if has_errors else 'CLEAN'}")
    return not has_errors


def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

    parser = argparse.ArgumentParser(description="Unity Log Inspector & Diagnostics Tool")
    parser.add_argument("--file", help="Path to specific log file (defaults to Logs/Editor.log or Editor-prev.log)")
    parser.add_argument("--errors", action="store_true", help="Filter strictly for errors, exceptions, and test failures")
    parser.add_argument("--compilation", action="store_true", help="Isolate C# and Burst compilation messages")
    parser.add_argument("--tests", action="store_true", help="Isolate test runner status and exit codes")
    parser.add_argument("--tail", type=int, default=30, help="Number of recent filtered lines to show (default: 30)")
    parser.add_argument("--list", action="store_true", help="List all discovered Unity log files")

    args = parser.parse_args()

    if args.list:
        list_logs(project_root)
        return

    log_file = resolve_log_file(project_root, args.file)

    mode = "summary"
    if args.errors:
        mode = "errors"
    elif args.compilation:
        mode = "compilation"
    elif args.tests:
        mode = "tests"

    success = inspect_log(log_file, mode=mode, tail_count=args.tail)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

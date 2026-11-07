#!/usr/bin/env python3
"""
Unity Test Automation and Reporting Script.
Ukrainian Warfare Project.

Features:
- Fast C# compilation pre-check via dotnet build (ci/FastCompile/FastCompile.csproj)
- Targeted Unity EditMode/PlayMode execution with --filter
- NUnit 3 XML report parsing and structured evidence formatting
- Standalone XML parsing for existing test logs
"""

import argparse
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run_cmd(cmd, cwd=None):
    res = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return res.returncode, res.stdout, res.stderr


def run_fast_compile(project_root):
    fast_compile_proj = os.path.join(project_root, "ci", "FastCompile", "FastCompile.csproj")
    if not os.path.exists(fast_compile_proj):
        print(f"[FastCompile] Project not found at {fast_compile_proj}, skipping.", file=sys.stderr)
        return True

    print(">>> Running FastCompile gate (dotnet build ci/FastCompile/FastCompile.csproj)...")
    start = time.time()
    code, stdout, stderr = run_cmd(
        ["dotnet", "build", fast_compile_proj, "--configuration", "Release", "--nologo"],
        cwd=project_root,
    )
    elapsed = time.time() - start

    if code != 0:
        print(f"\n[FastCompile FAILED] (took {elapsed:.2f}s):", file=sys.stderr)
        print(stdout, file=sys.stderr)
        if stderr:
            print(stderr, file=sys.stderr)
        return False

    print(f"[FastCompile PASSED] in {elapsed:.2f}s (0 errors)")
    return True


def parse_nunit_xml(xml_path):
    if not os.path.exists(xml_path):
        print(f"ERROR: XML report not found at {xml_path}", file=sys.stderr)
        return False, []

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        print(f"ERROR: Failed to parse XML file {xml_path}: {e}", file=sys.stderr)
        return False, []

    total = int(root.attrib.get("total", 0))
    passed = int(root.attrib.get("passed", 0))
    failed = int(root.attrib.get("failed", 0))
    skipped = int(root.attrib.get("skipped", 0))
    duration = float(root.attrib.get("duration", 0.0))
    run_result = root.attrib.get("result", "Unknown")

    print("\n=======================================================")
    print("             UNITY TEST EXECUTION RESULTS              ")
    print("=======================================================")
    print(f"Overall Result : {run_result}")
    print(f"Total Tests    : {total}")
    print(f"Passed         : {passed}")
    print(f"Failed         : {failed}")
    print(f"Skipped        : {skipped}")
    print(f"Duration       : {duration:.2f}s")
    print(f"Report File    : {xml_path}")
    print("-------------------------------------------------------")

    passed_tests = []
    failed_tests = []

    for test_case in root.iter("test-case"):
        name = test_case.attrib.get("name", "UnnamedTest")
        result = test_case.attrib.get("result", "")
        tc_duration = float(test_case.attrib.get("duration", 0.0))

        if result == "Passed":
            passed_tests.append((name, tc_duration))
        elif result == "Failed":
            failure_elem = test_case.find("failure")
            msg = ""
            stack = ""
            if failure_elem is not None:
                m_elem = failure_elem.find("message")
                s_elem = failure_elem.find("stack-trace")
                if m_elem is not None and m_elem.text:
                    msg = m_elem.text.strip()
                if s_elem is not None and s_elem.text:
                    stack = s_elem.text.strip()
            failed_tests.append((name, tc_duration, msg, stack))

    if passed_tests:
        print(f"\nPassed Tests ({len(passed_tests)}):")
        for idx, (name, dur) in enumerate(passed_tests, 1):
            print(f"  {idx}. {name} ({dur:.3f}s)")

    if failed_tests:
        print(f"\nFAILED Tests ({len(failed_tests)}):", file=sys.stderr)
        for idx, (name, dur, msg, stack) in enumerate(failed_tests, 1):
            print(f"\n  [{idx}] FAIL: {name} ({dur:.3f}s)", file=sys.stderr)
            if msg:
                print(f"      Message: {msg}", file=sys.stderr)
            if stack:
                print(f"      Stack Trace:\n{stack}", file=sys.stderr)

    all_passed = (failed == 0 and total > 0)
    return all_passed, passed_tests


def cmd_run(args, project_root):
    # 1. FastCompile pre-check
    if not args.no_fast_compile:
        if not run_fast_compile(project_root):
            sys.exit(1)

    # 2. Output XML path
    output_xml = args.output
    if not output_xml:
        filter_slug = args.filter.replace(".", "_").replace("*", "") if args.filter else "all"
        output_xml = os.path.join(project_root, "Logs", f"test_{args.mode}_{filter_slug}.xml")

    os.makedirs(os.path.dirname(os.path.abspath(output_xml)), exist_ok=True)

    # 3. Construct unity test command
    cmd = [
        "unity", "test", ".",
        "--mode", args.mode,
        "--output", output_xml,
        "--timeout", str(args.timeout),
    ]
    if args.filter:
        cmd.extend(["--filter", args.filter])

    print(f"\n>>> Running Unity {args.mode} tests...")
    if args.filter:
        print(f"    Filter: {args.filter}")
    print(f"    Output: {output_xml}")

    start = time.time()
    code, stdout, stderr = run_cmd(cmd, cwd=project_root)
    elapsed = time.time() - start

    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)

    print(f">>> Unity test process finished in {elapsed:.2f}s (Exit code: {code})")

    # 4. Parse results XML
    success, _ = parse_nunit_xml(output_xml)
    if not success or code != 0:
        sys.exit(1)


def cmd_parse(args):
    success, _ = parse_nunit_xml(args.xml_file)
    if not success:
        sys.exit(1)


def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

    parser = argparse.ArgumentParser(description="Unity Test Automation & Reporting Tool")
    subparsers = parser.add_subparsers(dest="subcommand")

    # parse subcommand
    p_parse = subparsers.add_parser("parse", help="Parse an existing NUnit XML test report")
    p_parse.add_argument("xml_file", help="Path to NUnit results XML file")
    p_parse.set_defaults(func=cmd_parse)

    # default run arguments
    parser.add_argument("--mode", choices=["EditMode", "PlayMode"], default="EditMode", help="Test mode (default: EditMode)")
    parser.add_argument("--filter", help="Test filter pattern (e.g. 'RemediationPhase05To09Tests')")
    parser.add_argument("--output", help="Path to write NUnit results XML")
    parser.add_argument("--timeout", type=int, default=300, help="Process timeout in seconds (default: 300)")
    parser.add_argument("--no-fast-compile", action="store_true", help="Skip the fast C# compilation gate")

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_run(args, project_root)


if __name__ == "__main__":
    main()

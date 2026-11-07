#!/usr/bin/env python3
"""
Snapshot & Replay Verification Runner.
Ukrainian Warfare Project.

Discovers, executes, and audits EditMode tests covering:
- WriteSnapshot -> TryReadSnapshot round-trip serialization
- Checkpoint / restore determinism
- Bit-exact state hasher equality
"""

import argparse
import os
import subprocess
import sys
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
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def parse_snapshot_results(xml_path):
    if not os.path.exists(xml_path):
        print(f"ERROR: XML report not found at {xml_path}", file=sys.stderr)
        return False

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        print(f"ERROR: Failed to parse XML: {e}", file=sys.stderr)
        return False

    total = int(root.attrib.get("total", 0))
    passed = int(root.attrib.get("passed", 0))
    failed = int(root.attrib.get("failed", 0))

    print("\n=======================================================")
    print("      SNAPSHOT & REPLAY DETERMINISM REPORT             ")
    print("=======================================================")
    print(f"Total Snapshot/Restore Tests: {total}")
    print(f"Passed                      : {passed}")
    print(f"Failed                      : {failed}")
    print("-------------------------------------------------------")

    for tc in root.iter("test-case"):
        name = tc.attrib.get("name")
        res = tc.attrib.get("result")
        dur = float(tc.attrib.get("duration", 0.0))
        status = "[PASS]" if res == "Passed" else "[FAIL]"
        print(f"{status} {name} ({dur:.3f}s)")

    print("-------------------------------------------------------")
    all_ok = (failed == 0 and total > 0)
    print(f"SNAPSHOT_INTEGRITY: {'PASS' if all_ok else 'FAIL'}")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Snapshot & Replay Verification Runner")
    parser.add_argument("--output", help="Path to write NUnit results XML")
    parser.add_argument("--parse", help="Parse existing results XML without re-running tests")
    parser.add_argument("--timeout", type=int, default=300, help="Process timeout in seconds")

    args = parser.parse_args()
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

    if args.parse:
        ok = parse_snapshot_results(args.parse)
        sys.exit(0 if ok else 1)

    output_xml = args.output or os.path.join(project_root, "Logs", "snapshot_verification.xml")
    filter_pattern = "*Snapshot*|*Restore*|*Determinism*|*Resumption*"

    print(f">>> Running Snapshot & Replay Tests (Filter: {filter_pattern})...")
    cmd = [
        "unity", "test", ".",
        "--mode", "EditMode",
        "--filter", filter_pattern,
        "--output", output_xml,
        "--timeout", str(args.timeout),
    ]

    code, stdout, stderr = run_cmd(cmd, cwd=project_root)
    print(f"Process finished with exit code {code}")

    ok = parse_snapshot_results(output_xml)
    sys.exit(0 if (ok and code == 0) else 1)


if __name__ == "__main__":
    main()

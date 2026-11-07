#!/usr/bin/env python3
"""
Pair Gate Verification Runner.
Ukrainian Warfare Project.

Automates the execution and report aggregation for project pair gates:
- Pair Gate A (after Phase 05 + Phase 06 independent review closure)
- Pair Gate B (after Phase 07 + Phase 08 independent review closure)
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
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def parse_xml_summary(xml_path):
    if not os.path.exists(xml_path):
        return None
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        total = int(root.attrib.get("total", 0))
        passed = int(root.attrib.get("passed", 0))
        failed = int(root.attrib.get("failed", 0))
        duration = float(root.attrib.get("duration", 0.0))
        result = root.attrib.get("result", "Unknown")
        return {
            "path": xml_path,
            "total": total,
            "passed": passed,
            "failed": failed,
            "duration": duration,
            "result": result,
        }
    except Exception as e:
        print(f"Warning: Failed to parse XML from {xml_path}: {e}", file=sys.stderr)
        return None


def generate_gate_report(gate_name, results, fast_compile_ok, output_path=None):
    lines = [
        f"# Pair Gate {gate_name} Verification Report",
        "",
        f"**Date/Time**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
        f"**FastCompile Core Build**: {'PASS (0 errors)' if fast_compile_ok else 'FAILED'}",
        "",
        "## Suite Results Summary",
        "",
        "| Suite / Fixture | Result | Total | Passed | Failed | Duration | Report File |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    all_passed = fast_compile_ok
    total_tests = 0
    total_passed = 0
    total_failed = 0
    total_duration = 0.0

    for res in results:
        name = res["name"]
        data = res.get("data")
        if data:
            status = "**PASS**" if data["failed"] == 0 and data["total"] > 0 else "**FAIL**"
            if data["failed"] > 0 or data["total"] == 0:
                all_passed = False
            total_tests += data["total"]
            total_passed += data["passed"]
            total_failed += data["failed"]
            total_duration += data["duration"]
            file_rel = os.path.relpath(data["path"])
            lines.append(f"| {name} | {status} | {data['total']} | {data['passed']} | {data['failed']} | {data['duration']:.2f}s | `{file_rel}` |")
        else:
            all_passed = False
            lines.append(f"| {name} | **MISSING / FAILED** | - | - | - | - | - |")

    lines.extend([
        "",
        f"**Totals**: {total_tests} tests executed ({total_passed} passed, {total_failed} failed) in {total_duration:.2f}s",
        "",
        "## Gate Verdict",
        "",
        f"**PAIR_GATE_{gate_name}_STATUS**: **{'PASS' if all_passed else 'BLOCKED'}**",
    ])

    report_content = "\n".join(lines) + "\n"

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"\nGate report written to: {output_path}")

    print("\n" + report_content)
    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Pair Gate Verification Runner")
    parser.add_argument("--gate", choices=["A", "B"], default="A", help="Pair Gate to execute (default: A)")
    parser.add_argument("--report-only", action="store_true", help="Compile report from existing XMLs without re-running tests")
    parser.add_argument("--output", help="Output path for markdown gate report")

    args = parser.parse_args()
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

    report_path = args.output or os.path.join(project_root, "Logs", f"pair_gate_{args.gate}_report.md")

    # Define suites per gate
    if args.gate == "A":
        suites = [
            {"name": "EditMode Full", "mode": "EditMode", "filter": None, "xml": os.path.join(project_root, "Logs", "gate_a_editmode.xml")},
            {"name": "PlayMode Full", "mode": "PlayMode", "filter": None, "xml": os.path.join(project_root, "Logs", "gate_a_playmode.xml")},
            {"name": "Navigation & Remediation", "mode": "EditMode", "filter": "RemediationPhase05To09Tests", "xml": os.path.join(project_root, "Logs", "gate_a_remediation.xml")},
        ]
    else:
        suites = [
            {"name": "EditMode Full", "mode": "EditMode", "filter": None, "xml": os.path.join(project_root, "Logs", "gate_b_editmode.xml")},
            {"name": "PlayMode Full", "mode": "PlayMode", "filter": None, "xml": os.path.join(project_root, "Logs", "gate_b_playmode.xml")},
            {"name": "Perception & Combat", "mode": "EditMode", "filter": "FixtureF03Tests|FixtureF04Tests", "xml": os.path.join(project_root, "Logs", "gate_b_fixtures.xml")},
        ]

    # FastCompile check
    fast_compile_ok = True
    if not args.report_only:
        print(">>> 1. Executing FastCompile gate...")
        fc_code, fc_out, _ = run_cmd(["dotnet", "build", "ci/FastCompile/FastCompile.csproj", "--configuration", "Release", "--nologo"], cwd=project_root)
        fast_compile_ok = (fc_code == 0)
        if not fast_compile_ok:
            print("ERROR: FastCompile failed:\n" + fc_out, file=sys.stderr)
            sys.exit(1)

        # Run test suites
        for s in suites:
            print(f"\n>>> Executing {s['name']}...")
            cmd = ["unity", "test", ".", "--mode", s["mode"], "--output", s["xml"], "--timeout", "600"]
            if s["filter"]:
                cmd.extend(["--filter", s["filter"]])
            code, out, err = run_cmd(cmd, cwd=project_root)
            print(f"    Finished with exit code {code}")

    # Gather results
    results = []
    for s in suites:
        summary = parse_xml_summary(s["xml"])
        results.append({
            "name": s["name"],
            "data": summary,
        })

    success = generate_gate_report(args.gate, results, fast_compile_ok, report_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

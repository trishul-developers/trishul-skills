#!/usr/bin/env python3
"""
Simulation Contract & Architecture Invariant Scanner.
Ukrainian Warfare Project.

Checks C# simulation code for:
- UnityEngine.Random usage (must use deterministic RNG)
- UnityEngine.Transform / GameObject in Runtime simulation state
- System.Collections.Generic.Dictionary / HashSet iteration in hot paths
- System.Linq usage in Runtime hot paths
- Capacity / bounded storage creep
"""

import argparse
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


RULES = [
    {
        "id": "R01_DETERMINISTIC_RNG",
        "pattern": re.compile(r"\bUnityEngine\.Random\b"),
        "severity": "ERROR",
        "scope": r"Runtime|Contracts",
        "message": "Authoritative simulation must use deterministic RNG (e.g. Unity.Mathematics.Random), never UnityEngine.Random.",
    },
    {
        "id": "R02_NO_SCENE_TRANSFORM_IN_RUNTIME",
        "pattern": re.compile(r"\b(UnityEngine\.)?(Transform|GameObject|MonoBehaviour|Component)\b"),
        "severity": "ERROR",
        "scope": r"Runtime[\\/]",
        "message": "Runtime authoritative simulation must not depend on Unity scene GameObjects/Transforms.",
    },
    {
        "id": "R03_NON_DETERMINISTIC_COLLECTION",
        "pattern": re.compile(r"\b(Dictionary|HashSet)<"),
        "severity": "WARNING",
        "scope": r"Runtime[\\/]",
        "message": "Dictionary/HashSet iteration order is non-deterministic. Use NativeParallelHashMap or sort keys.",
    },
    {
        "id": "R04_NO_LINQ_IN_RUNTIME",
        "pattern": re.compile(r"\busing\s+System\.Linq\b"),
        "severity": "WARNING",
        "scope": r"Runtime[\\/]",
        "message": "LINQ generates garbage allocations in hot simulation paths. Use imperative loops or native collections.",
    },
    {
        "id": "R05_CAPACITY_CREEP",
        "pattern": re.compile(r"\b(const\s+int\s+\w*Cap\w*|Capacity\s*=)\s*(\d+)"),
        "severity": "INFO",
        "scope": r"Runtime[\\/]|Tests[\\/]",
        "message": "Capacity assignment detected. Verify this does not silently mask an admission or lifetime defect.",
    },
]


def run_cmd(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return res.returncode, res.stdout, res.stderr


def audit_lines(file_path, lines):
    violations = []
    normalized_path = file_path.replace("\\", "/")

    for line_idx, line in enumerate(lines, 1):
        # Skip pure comments
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue

        for rule in RULES:
            if re.search(rule["scope"], normalized_path):
                if rule["pattern"].search(line):
                    violations.append({
                        "file": file_path,
                        "line": line_idx,
                        "id": rule["id"],
                        "severity": rule["severity"],
                        "message": rule["message"],
                        "content": stripped[:90],
                    })
    return violations


def audit_file(file_path):
    if not file_path.endswith(".cs") or not os.path.isfile(file_path):
        return []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return audit_lines(file_path, lines)


def audit_git_diff(range_arg=None):
    cmd = ["git", "diff", "--unified=0"]
    if range_arg:
        cmd.append(range_arg)

    code, stdout, _ = run_cmd(cmd)
    if code != 0:
        print("ERROR: Failed to run git diff", file=sys.stderr)
        sys.exit(1)

    violations = []
    current_file = None
    current_line = 0

    for line in stdout.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
        elif line.startswith("@@"):
            # @@ -a,b +c,d @@
            match = re.search(r"\+(\d+)", line)
            if match:
                current_line = int(match.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            added_text = line[1:]
            if current_file and current_file.endswith(".cs"):
                v = audit_lines(current_file, [added_text])
                for item in v:
                    item["line"] = current_line
                    violations.append(item)
            current_line += 1
        elif not line.startswith("-"):
            current_line += 1

    return violations


def print_report(violations):
    print("\n=======================================================")
    print("        SIMULATION CONTRACT AUDIT REPORT               ")
    print("=======================================================")

    errors = [v for v in violations if v["severity"] == "ERROR"]
    warnings = [v for v in violations if v["severity"] == "WARNING"]
    infos = [v for v in violations if v["severity"] == "INFO"]

    print(f"Total Findings: {len(violations)} (Errors: {len(errors)}, Warnings: {len(warnings)}, Info: {len(infos)})")
    print("-------------------------------------------------------")

    if not violations:
        print("PASS: No simulation contract violations detected.")
        return True

    for v in violations:
        tag = f"[{v['severity']}] {v['id']}"
        print(f"\n{tag} in {v['file']}:{v['line']}")
        print(f"  Issue: {v['message']}")
        print(f"  Code : {v['content']}")

    print("\n-------------------------------------------------------")
    if errors:
        print(f"FAILED: {len(errors)} architectural error(s) must be resolved.")
        return False
    else:
        print("PASSED with warnings/info.")
        return True


def main():
    parser = argparse.ArgumentParser(description="Simulation contract and invariant scanner")
    parser.add_argument("--diff", action="store_true", help="Audit uncommitted git changes (staged and unstaged)")
    parser.add_argument("--range", help="Audit git diff between revisions (e.g. 'HEAD~1..HEAD' or 'start_sha..HEAD')")
    parser.add_argument("--path", help="Audit a specific file or directory")

    args = parser.parse_args()

    if args.diff:
        violations = audit_git_diff()
    elif args.range:
        violations = audit_git_diff(args.range)
    elif args.path:
        violations = []
        if os.path.isfile(args.path):
            violations.extend(audit_file(args.path))
        else:
            for root, _, files in os.walk(args.path):
                for f in files:
                    if f.endswith(".cs"):
                        violations.extend(audit_file(os.path.join(root, f)))
    else:
        # Default: audit diff
        violations = audit_git_diff()

    passed = print_report(violations)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

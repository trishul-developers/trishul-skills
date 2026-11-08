#!/usr/bin/env python3
r"""Validation and linting tool for Skills in the repository.

Checks:
  - YAML frontmatter in all SKILL.md files (name, description)
  - Python script syntax via py_compile
  - Node.js script syntax via node --check
  - Unit tests via node --test (if test suites present)
"""

import os
import py_compile
import re
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = WORKSPACE_ROOT / "skills"


def parse_frontmatter(content: str) -> dict:
    meta = {}
    if not content.startswith("---"):
        return meta
    parts = content.split("---", 2)
    if len(parts) < 3:
        return meta
    for line in parts[1].strip().splitlines():
        m = re.match(r"^([a-zA-Z0-9_-]+)\s*:\s*(.*)$", line)
        if m and not line.startswith(" "):
            meta[m.group(1).strip()] = m.group(2).strip().strip("\"'")
    return meta


def validate() -> int:
    print(f"Validating skills under {SKILLS_DIR}...")
    errors = []
    warnings = []
    checked_skills = 0
    checked_py_scripts = 0
    checked_cli_helps = 0
    checked_js_scripts = 0
    test_files_run = 0

    for root, dirs, files in os.walk(SKILLS_DIR):
        # Skip node_modules, cache dirs
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", ".venv"}]

        for f in files:
            file_path = Path(root) / f

            if f.lower() == "skill.md":
                checked_skills += 1
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    errors.append(f"Cannot read {file_path}: {e}")
                    continue

                if not content.startswith("---"):
                    warnings.append(f"{file_path}: Missing YAML frontmatter marker '---'")
                else:
                    meta = parse_frontmatter(content)
                    if "name" not in meta:
                        warnings.append(f"{file_path}: Missing 'name' in frontmatter")
                    if "description" not in meta:
                        warnings.append(f"{file_path}: Missing 'description' in frontmatter")

            elif f.endswith(".py"):
                checked_py_scripts += 1
                try:
                    py_compile.compile(str(file_path), doraise=True)
                except py_compile.PyCompileError as e:
                    errors.append(f"Python syntax error in {file_path}: {e}")

                # Verify --help executes cleanly with code 0 on all CLI entrypoint scripts
                if "scripts" in file_path.parts and not f.startswith("test_") and f != "__init__.py":
                    checked_cli_helps += 1
                    help_res = subprocess.run(
                        [sys.executable, str(file_path), "--help"],
                        capture_output=True,
                        text=True,
                    )
                    if help_res.returncode != 0:
                        errors.append(
                            f"CLI script --help failure in {file_path} (exit code {help_res.returncode}):\n"
                            f"{help_res.stderr.strip() or help_res.stdout.strip()}"
                        )

                if f.startswith("test_") and "tests" in file_path.parts:
                    test_files_run += 1
                    test_res = subprocess.run(
                        [sys.executable, "-m", "unittest", str(file_path)],
                        capture_output=True,
                        text=True,
                    )
                    if test_res.returncode != 0:
                        errors.append(f"Python test failure in {file_path}:\n{test_res.stderr.strip() or test_res.stdout.strip()}")

            elif f.endswith((".js", ".mjs")):
                checked_js_scripts += 1
                res = subprocess.run(
                    ["node", "--check", str(file_path)],
                    capture_output=True,
                    text=True,
                )
                if res.returncode != 0:
                    errors.append(f"JavaScript/ESM syntax error in {file_path}:\n{res.stderr.strip()}")

            if f.endswith(".test.mjs"):
                test_files_run += 1
                test_res = subprocess.run(
                    ["node", "--test", str(file_path)],
                    capture_output=True,
                    text=True,
                )
                if test_res.returncode != 0:
                    errors.append(f"Test failure in {file_path}:\n{test_res.stderr.strip() or test_res.stdout.strip()}")

    print(f"Validation complete:")
    print(f"  - Skills checked: {checked_skills}")
    print(f"  - Python scripts checked: {checked_py_scripts}")
    print(f"  - CLI scripts --help verified: {checked_cli_helps}")
    print(f"  - JS/ESM scripts checked: {checked_js_scripts}")
    print(f"  - Test suites executed: {test_files_run}")
    print(f"  - Errors: {len(errors)}")
    print(f"  - Warnings: {len(warnings)}")

    if warnings:
        print("\nWarnings:")
        for w in warnings[:10]:
            print(f"  [WARN] {w}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  [ERROR] {e}")
        return 1

    print("\nAll skills, scripts, and tests passed verification cleanly!")
    return 0


if __name__ == "__main__":
    sys.exit(validate())

#!/usr/bin/env python3
r"""Validation and linting tool for Skills in E:\Projects\Skills."""

import json
import os
import py_compile
import re
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(r"E:\Projects\Skills")
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
    checked_scripts = 0

    for root, dirs, files in os.walk(SKILLS_DIR):
        for f in files:
            if f.lower() == "skill.md":
                checked_skills += 1
                skill_path = Path(root) / f
                try:
                    content = skill_path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    errors.append(f"Cannot read {skill_path}: {e}")
                    continue

                if not content.startswith("---"):
                    warnings.append(f"{skill_path}: Missing YAML frontmatter marker '---'")
                else:
                    meta = parse_frontmatter(content)
                    if "name" not in meta:
                        warnings.append(f"{skill_path}: Missing 'name' in frontmatter")
                    if "description" not in meta:
                        warnings.append(f"{skill_path}: Missing 'description' in frontmatter")

            elif f.endswith(".py"):
                script_path = Path(root) / f
                checked_scripts += 1
                try:
                    py_compile.compile(str(script_path), doraise=True)
                except py_compile.PyCompileError as e:
                    errors.append(f"Python syntax error in {script_path}: {e}")

    print(f"Validation complete:")
    print(f"  - Skills checked: {checked_skills}")
    print(f"  - Python scripts checked: {checked_scripts}")
    print(f"  - Errors: {len(errors)}")
    print(f"  - Warnings: {len(warnings)}")

    if warnings:
        print("\nWarnings (top 10):")
        for w in warnings[:10]:
            print(f"  [WARN] {w}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  [ERROR] {e}")
        return 1

    print("\nAll skills and scripts passed verification cleanly!")
    return 0


if __name__ == "__main__":
    sys.exit(validate())

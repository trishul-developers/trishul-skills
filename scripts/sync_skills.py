#!/usr/bin/env python3
r"""Sync and catalog custom skills and scripts created by agents on this system into E:\Projects\Skills.

Layout:
  skills/headless/   - Universal CLI headless runners (codex-headless, agy-headless, claude-headless)
  skills/collected/  - Consolidated platform skills (github-pr-workflow, unity-pipeline, etc.)
  skills/projects/   - Project-specific skills (chatgpt-role-bridge, tte-*, handoff)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE_ROOT = Path(r"E:\Projects\Skills")
SKILLS_DIR = WORKSPACE_ROOT / "skills"
HEADLESS_DIR = SKILLS_DIR / "headless"
COLLECTED_DIR = SKILLS_DIR / "collected"
PROJECTS_DIR = SKILLS_DIR / "projects"
CATALOG_FILE = WORKSPACE_ROOT / "catalog.json"


def parse_frontmatter(content: str) -> Dict[str, str]:
    """Parse YAML frontmatter from a SKILL.md file."""
    meta: Dict[str, str] = {}
    if not content.startswith("---"):
        return meta
    parts = content.split("---", 2)
    if len(parts) < 3:
        return meta
    frontmatter_text = parts[1].strip()
    current_key = None
    current_val: List[str] = []

    for line in frontmatter_text.splitlines():
        if not line.strip():
            continue
        m = re.match(r"^([a-zA-Z0-9_-]+)\s*:\s*(.*)$", line)
        if m and not line.startswith(" "):
            if current_key:
                meta[current_key] = "\n".join(current_val).strip().strip("\"'")
            current_key = m.group(1).strip()
            rest = m.group(2).strip()
            if rest in (">", ">-", "|", "|-"):
                current_val = []
            else:
                current_val = [rest]
        else:
            if current_key:
                current_val.append(line.strip())

    if current_key:
        meta[current_key] = "\n".join(current_val).strip().strip("\"'")

    return meta


def build_catalog() -> List[Dict[str, Any]]:
    """Index all skills currently in skills/headless, skills/collected, skills/projects."""
    catalog_entries: List[Dict[str, Any]] = []

    categories = [
        ("headless", HEADLESS_DIR),
        ("collected", COLLECTED_DIR),
        ("projects", PROJECTS_DIR),
    ]

    for category, cat_dir in categories:
        if not cat_dir.exists():
            continue

        for skill_dir in sorted(cat_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                content = skill_md.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                print(f"Error reading {skill_md}: {e}", file=sys.stderr)
                continue

            meta = parse_frontmatter(content)
            name = meta.get("name") or skill_dir.name
            description = meta.get("description") or ""

            entry = {
                "name": name,
                "description": description[:500],
                "category": category,
                "local_path": str(skill_dir.relative_to(WORKSPACE_ROOT)),
                "has_scripts": (skill_dir / "scripts").is_dir(),
                "has_references": (skill_dir / "references").is_dir() or (skill_dir / "resources").is_dir(),
                "has_tests": (skill_dir / "tests").is_dir(),
            }
            catalog_entries.append(entry)

    return catalog_entries


def main():
    parser = argparse.ArgumentParser(description="Catalog skills in E:\\Projects\\Skills")
    parser.parse_args()

    print("Indexing skills from skills/headless/, skills/collected/, and skills/projects/...")
    catalog = build_catalog()
    catalog_sorted = sorted(catalog, key=lambda x: (x["category"], x["name"]))

    metadata = {
        "version": "4.0.0",
        "description": "Consolidated catalog of high-leverage agent skills across headless runners, collected platform workflows, and project bridges.",
        "total_skills": len(catalog_sorted),
        "categories": {
            "headless": sum(1 for s in catalog_sorted if s["category"] == "headless"),
            "collected": sum(1 for s in catalog_sorted if s["category"] == "collected"),
            "projects": sum(1 for s in catalog_sorted if s["category"] == "projects"),
        },
        "skills": catalog_sorted,
    }

    CATALOG_FILE.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nSuccessfully indexed {len(catalog_sorted)} skills.")
    print(f"Catalog written to {CATALOG_FILE}")
    for cat, count in metadata["categories"].items():
        print(f"  - skills/{cat}/: {count} skills")


if __name__ == "__main__":
    main()

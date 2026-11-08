#!/usr/bin/env python3
r"""Sync and catalog custom skills and scripts created by agents on this system.

Layout:
  skills/             - Consolidated platform skills & headless CLI runners
  skills/projects/    - Project-specific skills (chatgpt-role-bridge, tte-*, handoff)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = WORKSPACE_ROOT / "skills"
PROJECTS_DIR = SKILLS_DIR / "projects"
CATALOG_FILE = WORKSPACE_ROOT / "catalog.json"

HEADLESS_SKILL_NAMES = {"codex-headless", "agy-headless", "claude-headless"}


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


def index_skill_dir(skill_dir: Path, category: str) -> Dict[str, Any] | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    try:
        content = skill_md.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"Error reading {skill_md}: {e}", file=sys.stderr)
        return None

    meta = parse_frontmatter(content)
    name = meta.get("name") or skill_dir.name
    description = meta.get("description") or ""

    return {
        "name": name,
        "description": description[:500],
        "category": category,
        "local_path": str(skill_dir.relative_to(WORKSPACE_ROOT)),
        "has_scripts": (skill_dir / "scripts").is_dir(),
        "has_references": (skill_dir / "references").is_dir() or (skill_dir / "resources").is_dir(),
        "has_tests": (skill_dir / "tests").is_dir(),
    }


def build_catalog() -> List[Dict[str, Any]]:
    """Index all skills in skills/ and skills/projects/."""
    catalog_entries: List[Dict[str, Any]] = []

    # 1. Skills directly under skills/
    for item in sorted(SKILLS_DIR.iterdir()):
        if not item.is_dir() or item.name in {"projects", "headless", "collected", ".git", "__pycache__"}:
            continue
        category = "headless" if item.name in HEADLESS_SKILL_NAMES or item.name.endswith("-headless") else "platform"
        entry = index_skill_dir(item, category)
        if entry:
            catalog_entries.append(entry)

    # 2. Project-specific skills
    if PROJECTS_DIR.exists():
        for item in sorted(PROJECTS_DIR.iterdir()):
            if not item.is_dir():
                continue
            entry = index_skill_dir(item, "projects")
            if entry:
                catalog_entries.append(entry)

    return catalog_entries


def main():
    parser = argparse.ArgumentParser(description="Catalog skills in E:\\Projects\\Skills")
    parser.parse_args()

    print("Indexing skills from skills/ and skills/projects/...")
    catalog = build_catalog()
    catalog_sorted = sorted(catalog, key=lambda x: (x["category"], x["name"]))

    metadata = {
        "version": "4.3.0",
        "description": "Consolidated catalog of high-leverage agent skills across platform workflows, headless runners, and project bridges.",
        "total_skills": len(catalog_sorted),
        "categories": {
            "headless": sum(1 for s in catalog_sorted if s["category"] == "headless"),
            "platform": sum(1 for s in catalog_sorted if s["category"] == "platform"),
            "projects": sum(1 for s in catalog_sorted if s["category"] == "projects"),
        },
        "skills": catalog_sorted,
    }

    CATALOG_FILE.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nSuccessfully indexed {len(catalog_sorted)} skills.")
    print(f"Catalog written to {CATALOG_FILE}")
    for cat, count in metadata["categories"].items():
        print(f"  - {cat}: {count} skills")


if __name__ == "__main__":
    main()

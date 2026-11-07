#!/usr/bin/env python3
r"""Sync and catalog custom skills and scripts created by agents on this system into E:\Projects\Skills.

Layout:
  skills/headless/   - Universal CLI headless runners
  skills/collected/  - Custom platform skills (Antigravity, Codex, Claude)
  skills/projects/   - Project-specific skills (TTE, ACP, Agent Hub)
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE_ROOT = Path(r"E:\Projects\Skills")
SKILLS_DIR = WORKSPACE_ROOT / "skills"
HEADLESS_DIR = SKILLS_DIR / "headless"
COLLECTED_DIR = SKILLS_DIR / "collected"
PROJECTS_DIR = SKILLS_DIR / "projects"
CATALOG_FILE = WORKSPACE_ROOT / "catalog.json"

EXCLUDE_PATTERNS = {
    ".git", ".trash", "node_modules", ".venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "worktrees", "sessions", "archived_sessions"
}

CUSTOM_SOURCES = [
    {
        "category": "collected",
        "platform": "antigravity",
        "path": Path(r"C:\Users\tosum\.gemini\config\skills"),
    },
    {
        "category": "collected",
        "platform": "codex",
        "path": Path(r"C:\Users\tosum\.codex\skills\github-pr-comment-watcher"),
    },
    {
        "category": "collected",
        "platform": "claude",
        "path": Path(r"C:\Users\tosum\.claude\skills\agy-cli"),
    },
    {
        "category": "collected",
        "platform": "claude",
        "path": Path(r"C:\Users\tosum\.claude\skills\codex-cli"),
    },
    {
        "category": "projects",
        "platform": "trishul-tactical-engine",
        "path": Path(r"E:\Projects\trishul-tactical-engine\.agents\skills"),
    },
    {
        "category": "projects",
        "platform": "agent-control-plane",
        "path": Path(r"E:\Projects\agent-control-plane\.agents\skills\cloud-role-bridge"),
    },
    {
        "category": "projects",
        "platform": "trishul-agent-hub",
        "path": Path(r"E:\Projects\trishul-agent-hub\.agents\skills\handoff"),
    },
]


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


def copy_skill_directory(src_dir: Path, dest_dir: Path) -> None:
    """Recursively copy skill files, preserving helper scripts, references, and configs."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_PATTERNS and not d.startswith(".")]
        rel_root = Path(root).relative_to(src_dir)
        target_root = dest_dir / rel_root
        target_root.mkdir(parents=True, exist_ok=True)
        for f in files:
            if f.endswith((".exe", ".dll", ".node", ".tmp", ".log")):
                continue
            src_file = Path(root) / f
            dest_file = target_root / f
            try:
                shutil.copy2(src_file, dest_file)
            except Exception as e:
                print(f"Warning: could not copy {src_file}: {e}", file=sys.stderr)


def collect_skills() -> List[Dict[str, Any]]:
    catalog_entries: List[Dict[str, Any]] = []
    seen_destinations: set[str] = set()

    # 1. Index headless runners
    if HEADLESS_DIR.exists():
        for skill_dir in HEADLESS_DIR.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                skill_md_path = skill_dir / "SKILL.md"
                content = skill_md_path.read_text(encoding="utf-8", errors="replace")
                meta = parse_frontmatter(content)
                entry = {
                    "name": meta.get("name") or skill_dir.name,
                    "description": meta.get("description", "")[:500],
                    "category": "headless",
                    "origin_platform": "internal",
                    "original_path": str(skill_md_path),
                    "local_path": str(skill_dir.relative_to(WORKSPACE_ROOT)),
                    "has_scripts": (skill_dir / "scripts").is_dir(),
                    "has_references": (skill_dir / "references").is_dir(),
                }
                catalog_entries.append(entry)

    # 2. Collect from custom sources into collected/ and projects/
    for source in CUSTOM_SOURCES:
        src_path = source["path"]
        category = source["category"]
        platform = source["platform"]
        target_base = PROJECTS_DIR if category == "projects" else COLLECTED_DIR
        target_base.mkdir(parents=True, exist_ok=True)

        if not src_path.exists():
            continue

        candidate_dirs: List[Path] = []
        if (src_path / "SKILL.md").exists():
            candidate_dirs.append(src_path)
        else:
            for child in src_path.iterdir():
                if child.is_dir() and (child / "SKILL.md").exists():
                    candidate_dirs.append(child)

        for skill_dir in candidate_dirs:
            skill_md_path = skill_dir / "SKILL.md"
            try:
                content = skill_md_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                print(f"Error reading {skill_md_path}: {e}", file=sys.stderr)
                continue

            meta = parse_frontmatter(content)
            skill_name = meta.get("name") or skill_dir.name
            description = meta.get("description") or ""

            # Dedup handoff across projects vs collected
            dest_dir = target_base / skill_name
            if skill_name == "handoff" and category == "collected" and (PROJECTS_DIR / "handoff").exists():
                continue

            seen_destinations.add(str(dest_dir))
            copy_skill_directory(skill_dir, dest_dir)

            entry = {
                "name": skill_name,
                "description": description[:500],
                "category": category,
                "origin_platform": platform,
                "original_path": str(skill_md_path),
                "local_path": str(dest_dir.relative_to(WORKSPACE_ROOT)),
                "has_scripts": (dest_dir / "scripts").is_dir(),
                "has_references": (dest_dir / "references").is_dir() or (dest_dir / "assets").is_dir(),
            }
            catalog_entries.append(entry)

    return catalog_entries


def main():
    print("Syncing custom skills into skills/headless/, skills/collected/, and skills/projects/...")
    catalog = collect_skills()
    catalog_sorted = sorted(catalog, key=lambda x: (x["category"], x["name"]))

    metadata = {
        "version": "3.0.0",
        "description": "Catalog of custom skills created on this machine across headless runners, collected platform skills, and project skills.",
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

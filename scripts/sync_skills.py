#!/usr/bin/env python3
r"""Sync and catalog ONLY custom skills and scripts created by agents on this system into E:\Projects\Skills.

Excludes all public, marketplace, and provider-bundled skills.
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
COLLECTED_DIR = SKILLS_DIR / "collected"
CATALOG_FILE = WORKSPACE_ROOT / "catalog.json"

EXCLUDE_PATTERNS = {
    ".git", ".trash", "node_modules", ".venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "worktrees", "sessions", "archived_sessions"
}

# Strictly defined sources for custom skills created by agents on this machine
CUSTOM_SOURCES = [
    {
        "platform": "antigravity",
        "category": "user-custom",
        "path": Path(r"C:\Users\tosum\.gemini\config\skills"),
    },
    {
        "platform": "codex",
        "category": "user-custom",
        "path": Path(r"C:\Users\tosum\.codex\skills\github-pr-comment-watcher"),
    },
    {
        "platform": "claude",
        "category": "user-custom",
        "path": Path(r"C:\Users\tosum\.claude\skills\agy-cli"),
    },
    {
        "platform": "claude",
        "category": "user-custom",
        "path": Path(r"C:\Users\tosum\.claude\skills\codex-cli"),
    },
    {
        "platform": "projects",
        "category": "trishul-tactical-engine",
        "path": Path(r"E:\Projects\trishul-tactical-engine\.agents\skills"),
    },
    {
        "platform": "projects",
        "category": "agent-control-plane",
        "path": Path(r"E:\Projects\agent-control-plane\.agents\skills\cloud-role-bridge"),
    },
    {
        "platform": "projects",
        "category": "trishul-agent-hub",
        "path": Path(r"E:\Projects\trishul-agent-hub\.agents\skills\handoff"),
    },
    {
        "platform": "headless",
        "category": "cli-runners",
        "path": Path(r"E:\Projects\Skills\skills\headless"),
    },
    {
        "platform": "multi-agent-process",
        "category": "process-skills",
        "path": Path(r"E:\Projects\Skills\skills\multi-agent-process"),
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


def collect_custom_skills() -> List[Dict[str, Any]]:
    catalog_entries: List[Dict[str, Any]] = []
    seen_destinations: set[str] = set()

    for source in CUSTOM_SOURCES:
        src_path = source["path"]
        platform = source["platform"]
        category = source["category"]
        if not src_path.exists():
            continue

        is_internal_authored = platform in ("headless", "multi-agent-process")

        # Discover skill directories: either src_path itself has SKILL.md, or its children do
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

            if is_internal_authored:
                entry = {
                    "name": skill_name,
                    "description": description[:500],
                    "platform": platform,
                    "source_category": category,
                    "original_path": str(skill_md_path),
                    "local_path": str(skill_dir.relative_to(WORKSPACE_ROOT)),
                    "has_scripts": (skill_dir / "scripts").is_dir(),
                    "has_references": (skill_dir / "references").is_dir() or (skill_dir / "assets").is_dir(),
                }
                catalog_entries.append(entry)
                continue

            dest_subpath = Path(platform) / skill_name
            dest_full = COLLECTED_DIR / dest_subpath

            counter = 1
            while str(dest_full) in seen_destinations:
                dest_subpath = Path(platform) / f"{skill_name}_{category}_{counter}"
                dest_full = COLLECTED_DIR / dest_subpath
                counter += 1

            seen_destinations.add(str(dest_full))
            copy_skill_directory(skill_dir, dest_full)

            entry = {
                "name": skill_name,
                "description": description[:500],
                "platform": platform,
                "source_category": category,
                "original_path": str(skill_md_path),
                "local_path": str(dest_full.relative_to(WORKSPACE_ROOT)),
                "has_scripts": (dest_full / "scripts").is_dir(),
                "has_references": (dest_full / "references").is_dir() or (dest_full / "assets").is_dir(),
            }
            catalog_entries.append(entry)

    return catalog_entries


def main():
    print("Starting sync of CUSTOM skills created on this system...")
    if COLLECTED_DIR.exists():
        shutil.rmtree(COLLECTED_DIR)
    COLLECTED_DIR.mkdir(parents=True, exist_ok=True)

    catalog = collect_custom_skills()
    catalog_sorted = sorted(catalog, key=lambda x: (x["platform"], x["name"]))

    metadata = {
        "version": "2.0.0",
        "description": "Catalog of custom skills and scripts created by agents on this system, plus new headless CLI skills.",
        "total_skills": len(catalog_sorted),
        "platforms": {
            "headless": sum(1 for s in catalog_sorted if s["platform"] == "headless"),
            "multi-agent-process": sum(1 for s in catalog_sorted if s["platform"] == "multi-agent-process"),
            "antigravity": sum(1 for s in catalog_sorted if s["platform"] == "antigravity"),
            "codex": sum(1 for s in catalog_sorted if s["platform"] == "codex"),
            "claude": sum(1 for s in catalog_sorted if s["platform"] == "claude"),
            "projects": sum(1 for s in catalog_sorted if s["platform"] == "projects"),
        },
        "skills": catalog_sorted,
    }

    CATALOG_FILE.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nSuccessfully collected {len(catalog_sorted)} custom skills into {COLLECTED_DIR}")
    print(f"Catalog written to {CATALOG_FILE}")
    for p, count in metadata["platforms"].items():
        print(f"  - {p}: {count} skills")


if __name__ == "__main__":
    main()

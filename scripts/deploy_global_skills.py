#!/usr/bin/env python3
r"""Deploy the 7 universal/platform skills globally to Claude, Codex, Antigravity, and OpenCode,
and clean up duplicate/superseded skills across global and project scopes.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import List, Set

WORKSPACE_ROOT = Path(r"E:\Projects\Skills")
SKILLS_DIR = WORKSPACE_ROOT / "skills"

# The 7 universal / platform skills (strictly skills/*, not skills/projects/*)
GLOBAL_SKILL_NAMES = [
    "agy-headless",
    "claude-headless",
    "codex-headless",
    "engineering-orchestrator",
    "github-pr-workflow",
    "pr-handoff-lifecycle",
    "unity-pipeline",
]

# Obsolete / superseded skill names that should be removed from global provider scopes
OBSOLETE_GLOBAL_SKILLS = {
    "agy-cli",
    "codex-cli",
    "github-pr-comment-watcher",
    "github-pr-git-workflow",
    "pair-gate-verification",
    "sim-contract-audit",
    "snapshot-replay-verifier",
    "unity-log-inspector",
    "unity-testing-workflow",
    "handoff",  # project-specific to trishul-agent-hub, should not be in global provider scopes
}

# Provider global skill directories
PROVIDER_GLOBAL_DIRS = {
    "claude": Path(r"C:\Users\tosum\.claude\skills"),
    "codex": Path(r"C:\Users\tosum\.codex\skills"),
    "antigravity": Path(r"C:\Users\tosum\.gemini\config\skills"),
    "opencode": Path(r"C:\Users\tosum\.config\opencode\skills"),
}

# Directories inside provider roots that must NEVER be deleted
PROTECTED_ITEMS = {
    "synced",    # Claude internal sync
    ".system",   # Codex internal system skills
    "state",     # Antigravity runtime state (e.g. pr_watch_state.json)
    ".git",
    "node_modules",
}

EXCLUDE_COPY_PATTERNS = {
    "__pycache__", ".pytest_cache", ".git", ".venv"
}


def copy_skill(src_dir: Path, dest_dir: Path) -> None:
    """Copy a skill directory cleanly, omitting temp and cache files."""
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_COPY_PATTERNS and not d.startswith(".")]
        rel_path = Path(root).relative_to(src_dir)
        target_root = dest_dir / rel_path
        target_root.mkdir(parents=True, exist_ok=True)

        for f in files:
            if f.endswith((".pyc", ".tmp", ".log")):
                continue
            src_file = Path(root) / f
            dest_file = target_root / f
            shutil.copy2(src_file, dest_file)


def deploy_to_provider(provider_name: str, target_dir: Path) -> None:
    print(f"\n==========================================")
    print(f"Deploying to {provider_name.upper()}: {target_dir}")
    print(f"==========================================")

    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Clean obsolete / duplicate skills
    for item in target_dir.iterdir():
        if item.name in PROTECTED_ITEMS:
            print(f"  [KEEP PROTECTED] {item.name}")
            continue

        if item.name in OBSOLETE_GLOBAL_SKILLS:
            print(f"  [REMOVE OBSOLETE] {item.name}")
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)

    # 2. Deploy the 7 skills
    for skill_name in GLOBAL_SKILL_NAMES:
        src = SKILLS_DIR / skill_name
        dest = target_dir / skill_name
        if not src.exists():
            print(f"  [ERROR] Source skill {src} not found!", file=sys.stderr)
            continue

        print(f"  [DEPLOY] {skill_name} -> {dest}")
        copy_skill(src, dest)


def check_and_clean_projects() -> None:
    print(f"\n==========================================")
    print(f"Checking Project Scopes for Duplicate Global Skills")
    print(f"==========================================")

    project_roots = [
        Path(r"E:\Projects\agent-control-plane"),
        Path(r"E:\Projects\trishul-agent-hub"),
        Path(r"E:\Projects\trishul-tactical-engine"),
        Path(r"E:\Projects\trishul-p6g-stage"),
        Path(r"E:\Projects\tte-docs-followup"),
    ]

    # Global skills or obsolete tools that should not be duplicated in project scopes
    all_to_remove_from_projects = (set(GLOBAL_SKILL_NAMES) | OBSOLETE_GLOBAL_SKILLS) - {"handoff", "cloud-role-bridge"}

    for proj in project_roots:
        if not proj.exists():
            continue

        candidate_skill_dirs = [
            proj / ".agents" / "skills",
            proj / ".claude" / "skills",
            proj / ".codex" / "skills",
            proj / ".gemini" / "skills",
            proj / ".opencode" / "skills",
        ]

        for sdir in candidate_skill_dirs:
            if not sdir.exists():
                continue

            for item in sdir.iterdir():
                if item.name in all_to_remove_from_projects:
                    print(f"  [REMOVE PROJECT DUPLICATE] {item} (superseded by global skill)")
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                else:
                    print(f"  [KEEP PROJECT-SPECIFIC] {item.name} in {sdir}")


def main():
    print(f"Deploying 7 Global Skills from {SKILLS_DIR}...")
    for name in GLOBAL_SKILL_NAMES:
        print(f"  - {name}")

    # Deploy to all 4 providers
    for provider, target_path in PROVIDER_GLOBAL_DIRS.items():
        deploy_to_provider(provider, target_path)

    # Clean duplicates from project scopes
    check_and_clean_projects()

    print("\nGlobal deployment and cleanup completed successfully!")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
r"""Deploy universal/platform skills globally to Claude, Codex, Antigravity, and OpenCode,
and clean up duplicate/superseded skills across global and project scopes.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import List, Set, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = WORKSPACE_ROOT / "skills"
PROJECTS_DIR = SKILLS_DIR / "projects"

# Active universal / platform skills per provider (strictly skills/*, not skills/projects/*)
DEFAULT_PROVIDER_SKILLS = [
    "agent-delivery",
    "agy-headless",
    "codex-headless",
    "github-pr-workflow",
    "unity-pipeline",
]

PROVIDER_SKILLS = {
    "claude": DEFAULT_PROVIDER_SKILLS,
    "codex": ["unity-pipeline", "claude-headless"],
    "antigravity": DEFAULT_PROVIDER_SKILLS + ["claude-headless"],
    "opencode": DEFAULT_PROVIDER_SKILLS,
}

# Explicit allow-list of active TTE project skills (deployed to both .claude/skills and .agents/skills)
TTE_PROJECT_SKILLS = [
    "tte-content-pipeline",
    "tte-golden-recapture",
    "tte-phase-evidence",
]

# Obsolete / superseded / retired skill names that should be removed from global provider scopes
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
    "handoff",  # project-specific to trishul-agent-hub, retired with hub
    "hub-messenger",
    "pr-handoff-lifecycle",
    "engineering-orchestrator",
    "opencode-headless",
}

ALL_MANAGED_GLOBAL_SKILLS = set(DEFAULT_PROVIDER_SKILLS) | {"claude-headless"} | OBSOLETE_GLOBAL_SKILLS

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


def to_platform_path(p: Path) -> Path:
    """Translate Windows-style drive paths to WSL /mnt/<drive> paths if running under Linux."""
    if sys.platform != "win32":
        s = str(p)
        if len(s) >= 2 and s[1] == ":":
            drive = s[0].lower()
            rest = s[2:].replace("\\", "/")
            return Path(f"/mnt/{drive}{rest}")
    return p


def get_provider_targets() -> List[Tuple[str, Path]]:
    """Return all target provider global skill directories across Windows and Linux."""
    targets = [
        ("claude", to_platform_path(Path(r"C:\Users\tosum\.claude\skills"))),
        ("codex", to_platform_path(Path(r"C:\Users\tosum\.codex\skills"))),
        ("antigravity", to_platform_path(Path(r"C:\Users\tosum\.gemini\config\skills"))),
        ("opencode", to_platform_path(Path(r"C:\Users\tosum\.config\opencode\skills"))),
    ]
    if sys.platform != "win32":
        linux_scopes = [
            ("antigravity (linux)", Path.home() / ".gemini" / "config" / "skills"),
            ("codex (linux)", Path.home() / ".codex" / "skills"),
            ("opencode (linux)", Path.home() / ".config" / "opencode" / "skills"),
        ]
        for name, p in linux_scopes:
            targets.append((name, p))
    return targets


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
    provider_key = provider_name.split()[0].lower()
    allowed_skills = PROVIDER_SKILLS.get(provider_key, DEFAULT_PROVIDER_SKILLS)
    skills_to_remove = OBSOLETE_GLOBAL_SKILLS | (ALL_MANAGED_GLOBAL_SKILLS - set(allowed_skills))

    # 1. Clean obsolete / retired / disallowed skills
    for item in target_dir.iterdir():
        if item.name in PROTECTED_ITEMS:
            print(f"  [KEEP PROTECTED] {item.name}")
            continue

        if item.name in skills_to_remove:
            print(f"  [REMOVE OBSOLETE] {item.name}")
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)

    # 2. Deploy the allowed global skills for this provider
    for skill_name in allowed_skills:
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
        to_platform_path(Path(r"E:\Projects\agent-control-plane")),
        to_platform_path(Path(r"E:\Projects\trishul-tactical-engine")),
        to_platform_path(Path(r"E:\Projects\tte-docs-followup")),
    ]

    all_to_remove_from_projects = ALL_MANAGED_GLOBAL_SKILLS - {"cloud-role-bridge"}

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


def deploy_project_skills() -> None:
    print(f"\n==========================================")
    print(f"Deploying Project Skills to Dedicated Projects")
    print(f"==========================================")

    # 1. TTE project skills (explicit allow-list deployed to both .claude/skills and .agents/skills)
    tte_root = to_platform_path(Path(r"E:\Projects\trishul-tactical-engine"))
    if tte_root.exists() and PROJECTS_DIR.exists():
        for target_root in [tte_root / ".claude" / "skills", tte_root / ".agents" / "skills"]:
            target_root.mkdir(parents=True, exist_ok=True)
            for skill_name in TTE_PROJECT_SKILLS:
                src = PROJECTS_DIR / skill_name
                if not src.exists():
                    print(f"  [ERROR] Source TTE skill {src} not found!", file=sys.stderr)
                    continue
                dest = target_root / skill_name
                print(f"  [DEPLOY TTE SKILL] {skill_name} -> {dest}")
                copy_skill(src, dest)

    # 2. agent-control-plane (chatgpt-role-bridge)
    acp_root = to_platform_path(Path(r"E:\Projects\agent-control-plane"))
    if acp_root.exists() and (PROJECTS_DIR / "chatgpt-role-bridge").exists():
        for d in [acp_root / ".agents" / "skills", acp_root / ".claude" / "skills"]:
            if d.parent.exists():
                d.mkdir(parents=True, exist_ok=True)
                dest = d / "chatgpt-role-bridge"
                print(f"  [DEPLOY ACP SKILL] chatgpt-role-bridge -> {dest}")
                copy_skill(PROJECTS_DIR / "chatgpt-role-bridge", dest)


def main():
    print(f"Deploying global skills from {SKILLS_DIR}...")
    for provider, skills in PROVIDER_SKILLS.items():
        print(f"  - {provider}: {', '.join(skills)}")

    # Deploy to all provider targets
    for provider, target_path in get_provider_targets():
        deploy_to_provider(provider, target_path)

    # Clean duplicates from project scopes
    check_and_clean_projects()

    # Deploy project skills
    deploy_project_skills()

    print("\nGlobal deployment, project sync, and cleanup completed successfully!")


if __name__ == "__main__":
    main()

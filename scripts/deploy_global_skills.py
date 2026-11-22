#!/usr/bin/env python3
r"""Deploy skills globally or locally into any project, for any agent or all agents.

Cross-agent headless rule:
  An agent never receives its own `*-headless` skill (e.g., Claude skips
  `claude-headless`, Codex skips `codex-headless`, Antigravity skips `agy-headless`).

Examples:
  # List all active skills and per-agent defaults
  python scripts/deploy_global_skills.py --list

  # Install specific skills into a project for Claude and Codex/Antigravity (.agents)
  python scripts/deploy_global_skills.py --project E:\Projects\MyApp --skill unity-pipeline --skill github-pr-workflow --agent all

  # Install all platform/cross-agent skills into a project for Codex
  python scripts/deploy_global_skills.py --project E:\Projects\MyApp --agent codex

  # Deploy globally to all providers (with obsolete/self-headless cleanup)
  python scripts/deploy_global_skills.py --scope global --clean
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = WORKSPACE_ROOT / "skills"
PROJECTS_DIR = SKILLS_DIR / "projects"

# Core universal / platform skills (under skills/*)
PLATFORM_SKILL_NAMES = [
    "agent-delivery",
    "agy-headless",
    "agy-wsl-headless",
    "claude-headless",
    "codex-headless",
    "github-pr-workflow",
    "unity-pipeline",
]

# An agent does not need its own headless runner
SELF_HEADLESS_SKILLS = {
    "claude": {"claude-headless"},
    "codex": {"codex-headless"},
    "antigravity": {"agy-headless", "agy-wsl-headless"},
}


def skills_for_agent(agent: str) -> List[str]:
    """Return the default platform skill list for an agent, excluding its own headless skill(s)."""
    excluded = SELF_HEADLESS_SKILLS.get(agent, set())
    return [s for s in PLATFORM_SKILL_NAMES if s not in excluded]


PROVIDER_SKILLS: Dict[str, List[str]] = {
    "claude": skills_for_agent("claude"),
    "codex": skills_for_agent("codex"),
    "antigravity": skills_for_agent("antigravity"),
    "opencode": skills_for_agent("opencode"),
    "agents": list(PLATFORM_SKILL_NAMES),
}

# Explicit allow-list of active TTE project skills (deployed to both .claude/skills and .agents/skills)
TTE_PROJECT_SKILLS = [
    "tte-asset-pipeline",
    "tte-content-pipeline",
    "tte-golden-recapture",
    "tte-phase-evidence",
]

# Obsolete / superseded / retired skill names that should be removed when --clean is used
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

ALL_MANAGED_GLOBAL_SKILLS = set(PLATFORM_SKILL_NAMES) | OBSOLETE_GLOBAL_SKILLS

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

PROJECT_AGENT_SUBDIRS = {
    "claude": Path(".claude") / "skills",
    "codex": Path(".codex") / "skills",
    "antigravity": Path(".gemini") / "skills",
    "opencode": Path(".opencode") / "skills",
    "agents": Path(".agents") / "skills",
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


def get_global_provider_targets(agents: Optional[Set[str]] = None) -> List[Tuple[str, Path]]:
    """Return target provider global skill directories, optionally filtered by agent set."""
    all_targets = [
        ("claude", to_platform_path(Path(r"C:\Users\tosum\.claude\skills"))),
        ("codex", to_platform_path(Path(r"C:\Users\tosum\.codex\skills"))),
        ("antigravity", to_platform_path(Path(r"C:\Users\tosum\.gemini\config\skills"))),
        ("opencode", to_platform_path(Path(r"C:\Users\tosum\.config\opencode\skills"))),
    ]
    if sys.platform != "win32":
        all_targets.extend([
            ("antigravity (linux)", Path.home() / ".gemini" / "config" / "skills"),
            ("codex (linux)", Path.home() / ".codex" / "skills"),
            ("opencode (linux)", Path.home() / ".config" / "opencode" / "skills"),
        ])
    if not agents:
        return all_targets
    return [(name, path) for name, path in all_targets if name.split()[0].lower() in agents]


def resolve_skill_source(skill_name: str) -> Optional[Path]:
    """Find a skill directory in skills/<name> or skills/projects/<name>."""
    for base in (SKILLS_DIR, PROJECTS_DIR):
        candidate = base / skill_name
        if candidate.is_dir() and (candidate / "SKILL.md").is_file():
            return candidate
    return None


def list_available_skills() -> Dict[str, List[str]]:
    """Return active skill names grouped by source ('platform' and 'projects')."""
    platform = []
    for item in sorted(SKILLS_DIR.iterdir()):
        if item.is_dir() and item.name not in {"projects", "archive", "headless", "collected", ".git", "__pycache__"}:
            if (item / "SKILL.md").is_file():
                platform.append(item.name)
    projects = []
    if PROJECTS_DIR.is_dir():
        for item in sorted(PROJECTS_DIR.iterdir()):
            if item.is_dir() and (item / "SKILL.md").is_file():
                projects.append(item.name)
    return {"platform": platform, "projects": projects}


def copy_skill(src_dir: Path, dest_dir: Path, dry_run: bool = False) -> None:
    """Copy a skill directory cleanly, omitting temp and cache files."""
    if dry_run:
        return
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
            shutil.copy2(Path(root) / f, target_root / f)


def deploy_to_target(
    label: str,
    agent_key: str,
    target_dir: Path,
    skills: List[str],
    clean: bool = False,
    dry_run: bool = False,
) -> None:
    """Deploy a list of skills to a target directory, optionally pruning obsolete/disallowed skills."""
    print(f"\n==========================================")
    print(f"Deploying to {label.upper()}: {target_dir}")
    print(f"==========================================")

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    if clean and target_dir.exists():
        allowed_for_clean = set(PROVIDER_SKILLS.get(agent_key, skills)) | set(skills)
        skills_to_remove = OBSOLETE_GLOBAL_SKILLS | (ALL_MANAGED_GLOBAL_SKILLS - allowed_for_clean)
        for item in sorted(target_dir.iterdir()):
            if item.name in PROTECTED_ITEMS:
                print(f"  [KEEP PROTECTED] {item.name}")
                continue
            if item.name in skills_to_remove:
                print(f"  [REMOVE OBSOLETE] {item.name}")
                if not dry_run:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)

    for skill_name in skills:
        src = resolve_skill_source(skill_name)
        if not src:
            print(f"  [ERROR] Source skill '{skill_name}' not found under {SKILLS_DIR}", file=sys.stderr)
            continue
        dest = target_dir / skill_name
        prefix = "[DRY-RUN DEPLOY]" if dry_run else "[DEPLOY]"
        print(f"  {prefix} {skill_name} -> {dest}")
        copy_skill(src, dest, dry_run=dry_run)


def deploy_to_project(
    project_root: Path,
    agents: List[str],
    requested_skills: Optional[List[str]],
    clean: bool = False,
    dry_run: bool = False,
) -> None:
    """Deploy selected (or default cross-agent) skills into a project's agent skill directories."""
    if not project_root.exists():
        print(f"Error: project path does not exist: {project_root}", file=sys.stderr)
        sys.exit(2)

    target_agents = ["claude", "agents"] if "all" in agents else agents
    for agent in target_agents:
        subdir = PROJECT_AGENT_SUBDIRS.get(agent)
        if not subdir:
            print(f"  [WARN] Unknown project agent '{agent}', skipping", file=sys.stderr)
            continue
        if requested_skills and requested_skills != ["all"]:
            skills = requested_skills
        else:
            skills = PROVIDER_SKILLS.get(agent, PLATFORM_SKILL_NAMES)
        deploy_to_target(
            label=f"project:{agent}",
            agent_key=agent,
            target_dir=project_root / subdir,
            skills=skills,
            clean=clean,
            dry_run=dry_run,
        )


def check_and_clean_projects(dry_run: bool = False) -> None:
    print(f"\n==========================================")
    print(f"Checking Known Project Scopes for Obsolete Skills")
    print(f"==========================================")

    project_roots = [
        to_platform_path(Path(r"E:\Projects\agent-control-plane")),
        to_platform_path(Path(r"E:\Projects\trishul-tactical-engine")),
        to_platform_path(Path(r"E:\Projects\tte-docs-followup")),
    ]

    for proj in project_roots:
        if not proj.exists():
            continue
        for subdir in PROJECT_AGENT_SUBDIRS.values():
            sdir = proj / subdir
            if not sdir.exists():
                continue
            for item in sorted(sdir.iterdir()):
                if item.name in OBSOLETE_GLOBAL_SKILLS:
                    print(f"  [REMOVE OBSOLETE] {item}")
                    if not dry_run:
                        if item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item.unlink(missing_ok=True)


def deploy_known_project_skills(dry_run: bool = False) -> None:
    print(f"\n==========================================")
    print(f"Deploying Project-Specific Skills to Dedicated Projects")
    print(f"==========================================")

    tte_root = to_platform_path(Path(r"E:\Projects\trishul-tactical-engine"))
    if tte_root.exists():
        for agent in ("claude", "agents"):
            deploy_to_target(
                label=f"tte:{agent}",
                agent_key=agent,
                target_dir=tte_root / PROJECT_AGENT_SUBDIRS[agent],
                skills=TTE_PROJECT_SKILLS,
                clean=False,
                dry_run=dry_run,
            )

    acp_root = to_platform_path(Path(r"E:\Projects\agent-control-plane"))
    if acp_root.exists() and resolve_skill_source("chatgpt-role-bridge"):
        for agent in ("agents", "claude"):
            target_dir = acp_root / PROJECT_AGENT_SUBDIRS[agent]
            if target_dir.parent.exists():
                deploy_to_target(
                    label=f"acp:{agent}",
                    agent_key=agent,
                    target_dir=target_dir,
                    skills=["chatgpt-role-bridge"],
                    clean=False,
                    dry_run=dry_run,
                )


def parse_multi(values: Optional[Iterable[str]]) -> List[str]:
    out: List[str] = []
    for val in values or []:
        for part in val.split(","):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Deploy skills globally or locally into a project, for any agent or all agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--scope",
        choices=["global", "project"],
        help="Deployment scope ('global' or 'project'; implied as 'project' when --project is given).",
    )
    ap.add_argument(
        "--project",
        type=Path,
        help="Target project root directory for project-local deployment.",
    )
    ap.add_argument(
        "--agent",
        action="append",
        help="Target agent(s): claude, codex, antigravity, opencode, agents, or all (repeatable/comma-separated; default: all).",
    )
    ap.add_argument(
        "--skill",
        action="append",
        help="Skill name(s) to deploy, or 'all' for default agent set (repeatable/comma-separated).",
    )
    ap.add_argument(
        "--clean",
        action="store_true",
        help="Remove obsolete/retired/disallowed skills from target directories.",
    )
    ap.add_argument(
        "--sync-known-projects",
        action="store_true",
        help="Also sync dedicated project skills (TTE, agent-control-plane) and clean obsolete project copies.",
    )
    ap.add_argument(
        "--list",
        action="store_true",
        help="List all available active skills and per-agent defaults, then exit.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deployed or removed without modifying any files.",
    )
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)

    if args.list:
        avail = list_available_skills()
        print("Available platform/headless skills:", ", ".join(avail["platform"]))
        print("Available project-specific skills:", ", ".join(avail["projects"]))
        print("\nPer-agent defaults (cross-agent headless rule):")
        for agent, skills in PROVIDER_SKILLS.items():
            print(f"  - {agent}: {', '.join(skills)}")
        return 0

    scope = args.scope or ("project" if args.project else None)
    if scope is None and not args.sync_known_projects:
        ap.print_help()
        return 0

    agents = parse_multi(args.agent) or ["all"]
    requested_skills = parse_multi(args.skill) or None

    if scope == "project":
        if not args.project:
            ap.error("--project PATH is required when --scope project is used")
        deploy_to_project(
            project_root=to_platform_path(args.project.resolve()),
            agents=agents,
            requested_skills=requested_skills,
            clean=args.clean,
            dry_run=args.dry_run,
        )
    elif scope == "global":
        agent_filter = None if "all" in agents else set(a.lower() for a in agents)
        targets = get_global_provider_targets(agent_filter)
        if not targets:
            print(f"No matching global provider targets for --agent {agents}", file=sys.stderr)
            return 2
        for provider_label, target_path in targets:
            agent_key = provider_label.split()[0].lower()
            if requested_skills and requested_skills != ["all"]:
                skills = requested_skills
            else:
                skills = PROVIDER_SKILLS.get(agent_key, PLATFORM_SKILL_NAMES)
            deploy_to_target(
                label=provider_label,
                agent_key=agent_key,
                target_dir=target_path,
                skills=skills,
                clean=args.clean,
                dry_run=args.dry_run,
            )

    if args.sync_known_projects:
        check_and_clean_projects(dry_run=args.dry_run)
        deploy_known_project_skills(dry_run=args.dry_run)

    print("\nDeployment completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

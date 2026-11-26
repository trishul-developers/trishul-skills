#!/usr/bin/env python3
r"""Validation and linting tool for Skills in the repository.

Checks:
  - YAML frontmatter in all SKILL.md files (name, description)
  - Python script syntax via py_compile
  - Node.js script syntax via node --check
  - Unit tests via node --test (if test suites present)
"""

import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = WORKSPACE_ROOT / "skills"
PROJECTS_DIR = SKILLS_DIR / "projects"
CATALOG_FILE = WORKSPACE_ROOT / "catalog.json"
DEPLOY_SCRIPT = WORKSPACE_ROOT / "scripts" / "deploy_global_skills.py"
DEPLOY_TEST_SCRIPT = WORKSPACE_ROOT / "scripts" / "tests" / "test_deploy_global_skills.py"


def parse_frontmatter(content: str) -> dict:
    """Parse single-line and multi-line YAML frontmatter from a SKILL.md file."""
    content = content.lstrip("\ufeff")
    meta = {}
    if not content.startswith("---"):
        return meta
    parts = content.split("---", 2)
    if len(parts) < 3:
        return meta
    frontmatter_text = parts[1].strip()
    current_key = None
    current_val = []

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


def check_model_consistency(errors: list) -> None:
    """Verify model names are consistent and not stale across headless, quota, and delivery skills."""
    stale_codex = ("gpt-6.1-sol", "gpt-6-astra")
    stale_claude = ("claude-3-7-sonnet",)
    stale_agy_default = ("gemini-3.8-flash",)

    codex_script = SKILLS_DIR / "codex-headless" / "scripts" / "codex_headless.py"
    codex_skill = SKILLS_DIR / "codex-headless" / "SKILL.md"
    codex_quota_skill = SKILLS_DIR / "codex-quota" / "SKILL.md"
    codex_quota_script = SKILLS_DIR / "codex-quota" / "scripts" / "check_codex_quota.py"
    agy_script = SKILLS_DIR / "agy-headless" / "scripts" / "agy_headless.py"
    agy_skill = SKILLS_DIR / "agy-headless" / "SKILL.md"
    claude_script = SKILLS_DIR / "claude-headless" / "scripts" / "claude_headless.py"
    claude_skill = SKILLS_DIR / "claude-headless" / "SKILL.md"
    example_profile = SKILLS_DIR / "agent-delivery" / "profiles" / "example.json"

    default_model = None
    if codex_script.is_file():
        text = codex_script.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'^DEFAULT_MODEL\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if not m:
            errors.append(f"{codex_script}: Missing DEFAULT_MODEL definition")
        else:
            default_model = m.group(1)
            if default_model in stale_codex:
                errors.append(f"{codex_script}: DEFAULT_MODEL '{default_model}' is stale")

    for doc in (codex_skill, codex_quota_skill, codex_quota_script):
        if doc.is_file():
            text = doc.read_text(encoding="utf-8", errors="replace")
            for stale in stale_codex:
                if stale in text:
                    errors.append(f"{doc}: Contains stale model name '{stale}'")

    if codex_skill.is_file() and default_model:
        text = codex_skill.read_text(encoding="utf-8", errors="replace")
        if default_model not in text:
            errors.append(f"{codex_skill}: Does not mention codex_headless DEFAULT_MODEL '{default_model}'")

    if agy_script.is_file():
        text = agy_script.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'^DEFAULT_MODEL\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if not m:
            errors.append(f"{agy_script}: Missing DEFAULT_MODEL definition")
        else:
            agy_default = m.group(1)
            if agy_default in stale_agy_default:
                errors.append(f"{agy_script}: DEFAULT_MODEL '{agy_default}' is stale")
    if agy_skill.is_file():
        text = agy_skill.read_text(encoding="utf-8", errors="replace")
        for stale in stale_codex + stale_claude:
            if stale in text:
                errors.append(f"{agy_skill}: Contains stale model name '{stale}'")

    if claude_script.is_file():
        text = claude_script.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'^DEFAULT_MODEL\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if not m:
            errors.append(f"{claude_script}: Missing DEFAULT_MODEL definition")
        else:
            claude_default = m.group(1)
            if claude_default in stale_claude:
                errors.append(f"{claude_script}: DEFAULT_MODEL '{claude_default}' is stale")
    if claude_skill.is_file():
        text = claude_skill.read_text(encoding="utf-8", errors="replace")
        for stale in stale_claude + stale_codex:
            if stale in text:
                errors.append(f"{claude_skill}: Contains stale model name '{stale}'")

    if example_profile.is_file():
        raw = example_profile.read_text(encoding="utf-8", errors="replace")
        for stale in stale_codex + stale_claude:
            if stale in raw:
                errors.append(f"{example_profile}: Contains stale model name '{stale}'")
        try:
            prof = json.loads(raw)
        except json.JSONDecodeError as e:
            errors.append(f"{example_profile}: Invalid JSON: {e}")
            return
        codex_models = set()
        for role in prof.get("roles", {}).values():
            slots = [role.get("primary")] + list(role.get("fallbacks") or [])
            for slot in slots:
                if isinstance(slot, dict) and slot.get("provider") == "codex" and slot.get("model"):
                    codex_models.add(slot["model"])
        if default_model and codex_models and default_model not in codex_models:
            errors.append(
                f"{example_profile}: codex_headless DEFAULT_MODEL '{default_model}' not found in profile codex slots {sorted(codex_models)}"
            )


def check_catalog_and_deployer_sync(errors: list) -> None:
    """Verify catalog.json and deploy_global_skills.py PLATFORM_SKILL_NAMES are in sync with active skills."""
    active_non_project = set()
    for item in sorted(SKILLS_DIR.iterdir()):
        if item.is_dir() and item.name not in {"projects", "archive", "headless", "collected", ".git", "__pycache__"}:
            if (item / "SKILL.md").is_file():
                active_non_project.add(item.name)

    active_projects = set()
    if PROJECTS_DIR.is_dir():
        for item in sorted(PROJECTS_DIR.iterdir()):
            if item.is_dir() and (item / "SKILL.md").is_file():
                active_projects.add(item.name)

    all_active = active_non_project | active_projects

    if not CATALOG_FILE.is_file():
        errors.append(f"Missing catalog file: {CATALOG_FILE}")
    else:
        try:
            cat = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
            cat_entries = cat.get("skills", [])
            cat_names = {entry.get("name") for entry in cat_entries if isinstance(entry, dict)}
            if cat.get("total_skills") != len(cat_entries):
                errors.append(
                    f"{CATALOG_FILE}: total_skills ({cat.get('total_skills')}) != len(skills) ({len(cat_entries)})"
                )
            missing_in_catalog = sorted(all_active - cat_names)
            extra_in_catalog = sorted(cat_names - all_active)
            if missing_in_catalog:
                errors.append(f"{CATALOG_FILE}: Missing active skills: {missing_in_catalog}")
            if extra_in_catalog:
                errors.append(f"{CATALOG_FILE}: Stale skills not found on disk: {extra_in_catalog}")
        except json.JSONDecodeError as e:
            errors.append(f"{CATALOG_FILE}: Invalid JSON: {e}")

    if not DEPLOY_SCRIPT.is_file():
        errors.append(f"Missing deployer script: {DEPLOY_SCRIPT}")
    else:
        import runpy
        ns = runpy.run_path(str(DEPLOY_SCRIPT))
        platform_names = set(ns.get("PLATFORM_SKILL_NAMES") or [])
        missing_in_deployer = sorted(active_non_project - platform_names)
        extra_in_deployer = sorted(platform_names - active_non_project)
        if missing_in_deployer:
            errors.append(
                f"{DEPLOY_SCRIPT}: PLATFORM_SKILL_NAMES missing active non-project skills: {missing_in_deployer}"
            )
        if extra_in_deployer:
            errors.append(
                f"{DEPLOY_SCRIPT}: PLATFORM_SKILL_NAMES contains non-existent skills: {extra_in_deployer}"
            )


def validate() -> int:
    print(f"Validating skills under {SKILLS_DIR}...")
    errors = []
    warnings = []
    checked_skills = 0
    checked_py_scripts = 0
    checked_cli_helps = 0
    checked_js_scripts = 0
    test_files_run = 0

    with tempfile.TemporaryDirectory() as pyc_tmp_dir:
        tmp_pyc = str(Path(pyc_tmp_dir) / "check.pyc")
        for root, dirs, files in os.walk(SKILLS_DIR):
            # Skip archive, node_modules, cache dirs
            dirs[:] = [d for d in dirs if d not in {"archive", ".git", "node_modules", "__pycache__", ".venv"}]

            for f in files:
                file_path = Path(root) / f

                if f.lower() == "skill.md":
                    checked_skills += 1
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")
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
                        py_compile.compile(str(file_path), cfile=tmp_pyc, doraise=True)
                    except py_compile.PyCompileError as e:
                        errors.append(f"Python syntax error in {file_path}: {e}")

                    # Verify --help executes cleanly with code 0 on all CLI entrypoint scripts
                    if "scripts" in file_path.parts and not f.startswith("test_") and f != "__init__.py":
                        checked_cli_helps += 1
                        help_res = subprocess.run(
                            [sys.executable, "-B", str(file_path), "--help"],
                            capture_output=True,
                            text=True,
                        )
                        if help_res.returncode != 0:
                            errors.append(
                                f"CLI script --help failure in {file_path} (exit code {help_res.returncode}):\n"
                                f"{help_res.stderr.strip() or help_res.stdout.strip()}"
                            )
                        if f == "gh_helper.py":
                            for subcmd in [["ci", "wait", "--help"], ["ci", "digest", "--help"], ["ci-wait", "--help"], ["ci-digest", "--help"]]:
                                checked_cli_helps += 1
                                help_sub = subprocess.run(
                                    [sys.executable, "-B", str(file_path)] + subcmd,
                                    capture_output=True,
                                    text=True,
                                )
                                if help_sub.returncode != 0:
                                    errors.append(
                                        f"CLI script {' '.join(subcmd)} failure in {file_path} (exit code {help_sub.returncode}):\n"
                                        f"{help_sub.stderr.strip() or help_sub.stdout.strip()}"
                                    )
                    if f.startswith("test_") and "tests" in file_path.parts:
                        test_files_run += 1
                        test_res = subprocess.run(
                            [sys.executable, "-B", "-m", "unittest", str(file_path)],
                            capture_output=True,
                            text=True,
                        )
                        if test_res.returncode != 0:
                            errors.append(f"Python test failure in {file_path}:\n{test_res.stderr.strip() or test_res.stdout.strip()}")

                elif f.endswith((".js", ".mjs")):
                    checked_js_scripts += 1
                    node_bin = shutil.which("node") or shutil.which("node.exe")
                    if node_bin:
                        res = subprocess.run(
                            [node_bin, "--check", str(file_path)],
                            capture_output=True,
                            text=True,
                        )
                        if res.returncode != 0:
                            errors.append(f"JavaScript/ESM syntax error in {file_path}:\n{res.stderr.strip()}")
                    else:
                        warnings.append(f"Node binary not found on PATH; skipped check for {file_path}")

                if f.endswith(".test.mjs"):
                    test_files_run += 1
                    node_bin = shutil.which("node") or shutil.which("node.exe")
                    if node_bin:
                        test_res = subprocess.run(
                            [node_bin, "--test", str(file_path)],
                            capture_output=True,
                            text=True,
                        )
                        if test_res.returncode != 0:
                            errors.append(f"Test failure in {file_path}:\n{test_res.stderr.strip() or test_res.stdout.strip()}")
                    else:
                        warnings.append(f"Node binary not found on PATH; skipped test for {file_path}")

    if DEPLOY_TEST_SCRIPT.is_file():
        test_files_run += 1
        deploy_test_res = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", str(DEPLOY_TEST_SCRIPT)],
            capture_output=True,
            text=True,
        )
        if deploy_test_res.returncode != 0:
            errors.append(
                f"Python test failure in {DEPLOY_TEST_SCRIPT}:\n"
                f"{deploy_test_res.stderr.strip() or deploy_test_res.stdout.strip()}"
            )

    check_model_consistency(errors)
    check_catalog_and_deployer_sync(errors)

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

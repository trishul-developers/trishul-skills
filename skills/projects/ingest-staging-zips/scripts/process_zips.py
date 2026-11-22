#!/usr/bin/env python3
"""Auto-process *_TTE_Staging.zip packages into military_assets and tte-art-staging."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import re
import shutil
import sys
import zipfile
from pathlib import Path

DEFAULT_ZIPS_DIR = Path(r"E:\Projects\military_assets\zips")
DEFAULT_STAGING_ROOT = Path(r"E:\Projects\tte-art-staging")
DEFAULT_MILITARY_ROOT = Path(r"E:\Projects\military_assets")

REQUIRED_DOCS = ("MODEL_SHEET.md", "DELIVERY.md", "PROVENANCE.md")
BLEND_EXTS = {".blend", ".blend1", ".blend2"}
SHA256_ROW_RE = re.compile(r"\|\s*`([^`]+)`\s*\|\s*[0-9,]+\s*\|\s*`([0-9a-fA-F]{64})`\s*\|")


def sha256_file(path: Path) -> str:
    """Compute lowercase SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def derive_key(zip_path: Path) -> str:
    """Derive asset key from <Key>_TTE_Staging.zip filename."""
    name = zip_path.name
    if name.endswith("_TTE_Staging.zip"):
        return name[: -len("_TTE_Staging.zip")]
    return zip_path.stem


def validate_zip(zip_path: Path, key: str) -> tuple[list[str], int]:
    """Validate internal paths start strictly with <Key>/ and return (files, uncompressed_bytes)."""
    total_bytes = 0
    files: list[str] = []
    prefix = f"{key}/"
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            norm = info.filename.replace("\\", "/")
            if ".." in Path(norm).parts or norm.startswith("/"):
                raise ValueError(f"Unsafe zip entry in {zip_path.name}: {info.filename}")
            if not norm.startswith(prefix):
                raise ValueError(
                    f"Entry in {zip_path.name} does not start with '{prefix}': {info.filename}"
                )
            total_bytes += info.file_size
            if not info.is_dir():
                files.append(norm)
    return files, total_bytes


def move_inbox_zips(inbox: Path, pattern: str, zips_dir: Path, dry_run: bool) -> list[Path]:
    """Move matching zips from inbox into zips_dir before processing."""
    moved: list[Path] = []
    if not inbox.is_dir():
        raise FileNotFoundError(f"Inbox directory not found: {inbox}")
    for src in sorted(inbox.glob(pattern)):
        if not src.is_file():
            continue
        dst = zips_dir / src.name
        print(f"[INBOX] {src} -> {dst}")
        if not dry_run:
            zips_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        moved.append(dst)
    return moved


def copy_tree_contents(src: Path, dst: Path) -> None:
    """Copy directory contents from src into dst, overwriting existing files."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def verify_provenance_hashes(asset_dir: Path) -> tuple[int, list[str]]:
    """Verify binary FBX/PNG hashes recorded in PROVENANCE.md against extracted files."""
    prov_path = asset_dir / "PROVENANCE.md"
    if not prov_path.is_file():
        return 0, ["Missing PROVENANCE.md"]

    checked = 0
    mismatches: list[str] = []
    text = prov_path.read_text(encoding="utf-8", errors="replace")
    for rel_str, expected_hash in SHA256_ROW_RE.findall(text):
        rel = rel_str.replace("\\", "/")
        if not (rel.endswith(".fbx") or rel.endswith(".png")):
            continue
        candidate = asset_dir / rel
        if not candidate.is_file() and "/" not in rel:
            candidate = asset_dir / "textures" / rel
        if not candidate.is_file():
            continue
        actual = sha256_file(candidate)
        checked += 1
        if actual.lower() != expected_hash.lower():
            mismatches.append(f"{rel}: expected {expected_hash}, got {actual}")
    return checked, mismatches


def validate_staging_dir(asset_dir: Path, key: str, expect_renders: bool) -> list[str]:
    """Check Common §9 layout rules on the extracted staging folder."""
    issues: list[str] = []
    for doc in REQUIRED_DOCS:
        if not (asset_dir / doc).is_file():
            issues.append(f"Missing {doc}")
    if not (asset_dir / f"{key}_Collision.fbx").is_file():
        issues.append(f"Missing {key}_Collision.fbx")
    if not list(asset_dir.glob("*.fbx")):
        issues.append("No .fbx files in root")
    if not (asset_dir / "textures").is_dir() or not list((asset_dir / "textures").rglob("*.png")):
        issues.append("Missing or empty textures/")
    if (asset_dir / "source").exists():
        issues.append("source/ still present in staging")
    if expect_renders and not (asset_dir / "renders").is_dir():
        issues.append("Missing renders/")

    for f in asset_dir.iterdir():
        if f.is_file() and f.name not in REQUIRED_DOCS and f.suffix.lower() != ".fbx":
            issues.append(f"Stray root file: {f.name}")

    _, mismatches = verify_provenance_hashes(asset_dir)
    issues.extend(mismatches)
    return issues


def process_zip(
    zip_path: Path,
    staging_root: Path,
    military_root: Path,
    keep_renders_in_staging: bool,
    dry_run: bool,
) -> list[str]:
    """Extract a single zip and split into military_assets (full) and tte-art-staging (Unity)."""
    key = derive_key(zip_path)
    _, uncomp_bytes = validate_zip(zip_path, key)

    target_dir = staging_root / key
    dst_sources = military_root / "Sources" / key
    tools_name = "Leopard2A5_Kucher" if key == "Leopard2A5" else key
    dst_tools = military_root / "Tools" / "AssetSources" / tools_name
    dst_exports = military_root / "Exports" / key
    dst_previews = military_root / "Docs" / "AssetPreviews" / key

    if dry_run:
        print(f"[DRY-RUN] {key}: {uncomp_bytes / (1024 * 1024):.1f} MB -> staging + military_assets")
        return []

    if target_dir.exists():
        shutil.rmtree(target_dir)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(staging_root)

    # 1. Move source/ -> military_assets/Sources/<Key> & Tools/AssetSources/<Key>
    src_dir = target_dir / "source"
    if src_dir.is_dir():
        for item in list(src_dir.iterdir()):
            if item.is_file() and item.suffix.lower() in BLEND_EXTS:
                dst_sources.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(dst_sources / item.name))
            else:
                dst_tools.mkdir(parents=True, exist_ok=True)
                dest = dst_tools / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest))
        shutil.rmtree(src_dir)

    # 2. Copy handoff docs (*.md) -> Tools/AssetSources/<Key>
    dst_tools.mkdir(parents=True, exist_ok=True)
    for md in target_dir.glob("*.md"):
        shutil.copy2(md, dst_tools / md.name)

    # 3. Copy Unity objects (*.fbx + textures/) -> Exports/<Key>
    dst_exports.mkdir(parents=True, exist_ok=True)
    for fbx in target_dir.glob("*.fbx"):
        shutil.copy2(fbx, dst_exports / fbx.name)
    tex_dir = target_dir / "textures"
    if tex_dir.is_dir():
        copy_tree_contents(tex_dir, dst_exports / "textures")

    # 4. Copy (or move) renders/ -> Docs/AssetPreviews/<Key>
    rnd_dir = target_dir / "renders"
    if rnd_dir.is_dir():
        copy_tree_contents(rnd_dir, dst_previews)
        if not keep_renders_in_staging:
            shutil.rmtree(rnd_dir)

    return validate_staging_dir(target_dir, key, expect_renders=keep_renders_in_staging)


def matches_filters(key: str, patterns: list[str] | None) -> bool:
    """Return True if key matches any glob pattern (or no filter was provided)."""
    if not patterns:
        return True
    return any(fnmatch.fnmatch(key, pat) for pat in patterns)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest *_TTE_Staging.zip packages.")
    parser.add_argument("--zips-dir", type=Path, default=DEFAULT_ZIPS_DIR)
    parser.add_argument("--staging-root", type=Path, default=DEFAULT_STAGING_ROOT)
    parser.add_argument("--military-assets-root", type=Path, default=DEFAULT_MILITARY_ROOT)
    parser.add_argument("--inbox", type=Path, default=None, help="Optional folder to move new zips from.")
    parser.add_argument("--pattern", default="*.zip", help="Glob for --inbox (default: *.zip).")
    parser.add_argument("--keys", nargs="*", help="Optional key/glob filter (e.g. T72B3 Prop_*).")
    parser.add_argument("--force", action="store_true", help="Re-process even if <Key> exists in staging.")
    parser.add_argument("--no-renders-in-staging", action="store_true", help="Remove renders/ from staging.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without modifying files.")
    args = parser.parse_args()

    if args.inbox:
        move_inbox_zips(args.inbox, args.pattern, args.zips_dir, args.dry_run)

    if not args.zips_dir.is_dir():
        print(f"ERROR: zips directory not found: {args.zips_dir}", file=sys.stderr)
        return 1

    zips = sorted(args.zips_dir.glob("*.zip"))
    selected: list[Path] = []
    for z in zips:
        key = derive_key(z)
        if not matches_filters(key, args.keys):
            continue
        staged = args.staging_root / key
        if not args.force and staged.is_dir():
            continue
        selected.append(z)

    if not selected:
        print("All matching zip packages are already staged. Use --force to re-extract.")
        return 0

    free_gb = shutil.disk_usage(args.staging_root).free / (1024 ** 3)
    print(f"Selected {len(selected)} zip(s) to process (free space on target: {free_gb:.2f} GB).")

    all_issues: dict[str, list[str]] = {}
    for idx, z in enumerate(selected, 1):
        key = derive_key(z)
        issues = process_zip(
            z,
            staging_root=args.staging_root,
            military_root=args.military_assets_root,
            keep_renders_in_staging=not args.no_renders_in_staging,
            dry_run=args.dry_run,
        )
        status = "OK" if not issues else f"ISSUES({len(issues)})"
        print(f"[{idx}/{len(selected)}] {key}: {status}")
        if issues:
            all_issues[key] = issues

    if all_issues:
        print("\nValidation issues found:", file=sys.stderr)
        for key, errs in all_issues.items():
            for err in errs:
                print(f"  - {key}: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

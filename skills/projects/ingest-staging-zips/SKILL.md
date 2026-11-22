---
name: ingest-staging-zips
description: >-
  Auto-process *_TTE_Staging.zip asset packages from E:\Projects\military_assets\zips\
  (or an inbox folder) into the spec-compliant split between E:\Projects\tte-art-staging\
  (Unity FBX/PNG objects, handoff docs, and review renders) and E:\Projects\military_assets\
  (full source .blend files, build/QA scripts, exports, previews, and master zips).
  Use when new zipped 3D assets arrive or when asked to sync/extract packages from zips/.
---

# Ingest Staging Zips (`ingest-staging-zips`)

Automates the intake, validation, extraction, and repository split for `*_TTE_Staging.zip` packages according to `requirements/TTE_asset_requirements.md` and `requirements/TTE_vehicle_common.md` §9.

## Repository Split Rules

| Destination | Contents | Purpose |
|---|---|---|
| `E:\Projects\military_assets\zips\` | Master `*_TTE_Staging.zip` archives | Archived full delivery bundles |
| `E:\Projects\military_assets\Sources\<Key>\` | `.blend`, `.blend1`, `.blend2` | Authoritative Blender sources |
| `E:\Projects\military_assets\Tools\AssetSources\<Key>\` | `.py`, `.json`, reports, + copies of `.md` docs | Build, texture, and QA tooling/evidence |
| `E:\Projects\military_assets\Exports\<Key>\` | `*.fbx` + `textures\` | Unity-ready exports |
| `E:\Projects\military_assets\Docs\AssetPreviews\<Key>\` | `renders\` | Review and articulation renders |
| `E:\Projects\tte-art-staging\<Key>\` | `*.fbx`, `textures\`, `MODEL_SHEET.md`, `DELIVERY.md`, `PROVENANCE.md`, `renders\` | TTE handoff (Stage 2 `I1–I13` & Stage 3 Unity import; **no `source/`**, **no zips**) |

> **Note:** `renders\` is retained in `tte-art-staging\<Key>\` by default because TTE's `tte-asset-pipeline` Stage 2 (`I11`) inspects 150 m / 400 m renders read-only from staging, while Stage 3 copies only `.fbx` and `.png` into Unity. Pass `--no-renders-in-staging` if you only want `.fbx`, `textures\`, and `.md` files in staging.

## Quick Usage

Run the helper script [process_zips.py](./scripts/process_zips.py):

```powershell
# 1. Dry-run: check which zips in E:\Projects\military_assets\zips\ are not yet staged
python .agents/skills/ingest-staging-zips/scripts/process_zips.py --dry-run

# 2. Process all new/missing zips from E:\Projects\military_assets\zips\
python .agents/skills/ingest-staging-zips/scripts/process_zips.py

# 3. Intake newly downloaded zips (moves them to E:\Projects\military_assets\zips\ first, then processes)
python .agents/skills/ingest-staging-zips/scripts/process_zips.py --inbox "C:\Users\tosum\Downloads" --pattern "Prop_*.zip"

# 4. Force re-process specific keys (e.g. after a re-export)
python .agents/skills/ingest-staging-zips/scripts/process_zips.py --keys T72B3 BMP2 --force
```

## What the Script Checks

1. **Archive safety & naming:** Verifies every zip entry starts strictly with `<Key>/` (no path traversal or stray prefixes).
2. **Clean replacement:** On `--force` or when updating an existing `<Key>`, removes stale files (such as legacy `build_report.json` in root) before extracting.
3. **Spec §9 compliance:** Confirms `MODEL_SHEET.md`, `DELIVERY.md`, `PROVENANCE.md`, `<Key>_Collision.fbx`, `textures/`, and zero stray root files or leftover `source/` directories in `tte-art-staging\<Key>\`.
4. **SHA-256 verification:** Spot-checks extracted `.fbx`/`.png` hashes against `PROVENANCE.md` and reports any missing docs or hash mismatches.

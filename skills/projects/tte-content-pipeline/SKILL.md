---
name: tte-content-pipeline
description: Create, validate, and bake game content definition assets and register entries in the correct content-pack paths using scripts/validate_content_asset.py. Use when adding or changing units, weapons, sensors, factions, missions, or register values. Implementor or executor role.
---

# Content Pipeline & Register Validator (`tte-content-pipeline`)

Source of truth: D3 (`docs/design/D3_content_pipeline_register_catalog.md`), spec G01 amendments A2 (layout), A5 (ids, hashes, vocabulary). Code: `Assets/Scripts/Trishul/Authoring/Content/` (`DefinitionAsset`, `RegisterValueField`, `ContentBaker`, `BakeContext`, `RegisterImporter`, `ContentProject`) and `Runtime/Content/` (`BakedContent`, `ContentHash`, `ContentIds`, `RegisterVocabulary`).

---

## 1. Fast Offline Validation & Key Hashing

Use the dedicated validator to check candidate register files or compute `DefinitionId` hashes before launching Unity:

```powershell
# 1. Compute and verify a key's 32-bit FNV-1a DefinitionId
python "skills/projects/tte-content-pipeline/scripts/validate_content_asset.py" --key plc.mbt.a

# 2. Validate a candidate register JSON file against RegisterVocabulary
python "skills/projects/tte-content-pipeline/scripts/validate_content_asset.py" --file Assets/Content/Core/Register/core_register.json

# 3. Full tree audit for key syntax, unit vocabulary, and cross-pack FNV-1a collisions
python "skills/projects/tte-content-pipeline/scripts/validate_content_asset.py" -C Assets/Content
```

---

## 2. Directory Layout (Content Pack `Core`)

```
Assets/Content/Core/
  Definitions/<Family>/   Chassis, WeaponStation, Sensor, Signature, Doctrine, CrewTemplate,
                          VehicleVariant, UnitArchetype, Faction, ForceSet
  Missions/<MissionId>/   MissionDefinition and its world asset
  Register/*.json         register entries (D3 section 5 format); each pack has its own register
  Licenses/*.json         asset-licence register (may be empty)
```

- Content keys (`m_Key`) are **independent of folders**: moving a pack never changes a `DefinitionId`. Never reuse a key for a different item.
- Keys and tags are ASCII `[a-z0-9._-]` (keys: dot-separated non-empty segments, at most 96 characters), for example `plc.mbt.a`. `DefinitionId` = 32-bit FNV-1a of the key (never zero); any collision fails the bake.

---

## 3. Register Vocabulary & Invariants

Every tunable number is an entry in `Assets/Content/<Pack>/Register/*.json`:
```json
{
  "registerVersion": 1,
  "sources": [
    { "key": "src.x", "title": "Field Manual", "author": "MoD", "date": "2024", "url": "", "accessNote": "" }
  ],
  "entries": [
    {
      "key": "plc.mbt.a.mass",
      "quantity": "mass",
      "unit": "t",
      "value": 46,
      "evidence": "GameplayApproximation",
      "confidence": "Estimated"
    }
  ]
}
```

Closed vocabulary in `RegisterVocabulary`:
- `mass`: `kg`, `t`, `g`
- `length`: `m`, `km`, `mm`
- `range`: `m`, `km`
- `speed`: `m/s`, `km/h`
- `penetration_rha`: `mm` (`xQuantity`: `range`, `xUnit`: `m`)
- `time`: `s`, `ms`
- `angle`: `rad`, `deg`
- `angular_speed`: `rad/s`, `deg/s`
- `ratio`: `1`
- `count`: `1`
- `area`: `m2`
- `damage_points`: `dp`

Table values must have strictly ascending x-coordinates and define matching `xQuantity` and `xUnit`.
Placeholder keys under `plc.` must have `evidence: "GameplayApproximation"` and `confidence: "Estimated"`.

---

## 4. Unity Verification & Baking

Once register JSON passes offline validation, verify the bake in Unity via the global `unity-pipeline`:

```powershell
python "skills/unity-pipeline/scripts/unity_pipeline.py" test `
  -C "E:/Projects/trishul-tactical-engine" `
  --filter "Trishul.Tests.EditMode.Content.AllContentValidatesTests"
```
Or menu *Trishul / Validate All Content* (`ContentValidationMenu`).

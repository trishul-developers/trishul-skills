---
name: tte-content-asset
description: Create a game content definition asset plus its register and licence entries in the correct content-pack paths, then validate. Use when adding or changing units, weapons, sensors, factions, missions or register values. Implementor or executor.
---

# Content asset (implementor / executor)

Source of truth: D3 (`docs/design/D3_content_pipeline_register_catalog.md`), spec G01 amendments A2 (layout), A5 (ids, hashes, vocabulary). Code: `Assets/Scripts/Trishul/Authoring/Content/` (`DefinitionAsset`, `RegisterValueField`, `ContentBaker`, `BakeContext`, `RegisterImporter`, `ContentProject`) and `Runtime/Content/` (`BakedContent`, `ContentHash`, `ContentIds`, register model, `RegisterVocabulary`).

## Where things go (content pack `Core`; other packs mirror it)
```
Assets/Content/Core/
  Definitions/<Family>/   Chassis, WeaponStation, Sensor, Signature, Doctrine, CrewTemplate,
                          VehicleVariant, UnitArchetype, Faction, ForceSet
  Missions/<MissionId>/   MissionDefinition and its world asset
  Register/*.json         register entries (D3 section 5 format); each pack has its own register
  Licenses/*.json         asset-licence register (may be empty)
```
- Content keys (`m_Key`) are **independent of folders**: moving a pack never changes a `DefinitionId`. Never reuse a key for a different thing.
- Keys and tags are ASCII `[a-z0-9._-]` (keys: dot-separated non-empty segments, at most 96 characters), for example `plc.mbt.a`. Anything else is a validation error. `DefinitionId` = 32-bit FNV-1a of the key (never zero); **any collision fails the bake**: rename a key to resolve it (A5 Q90).
- Engine code is not content: it stays under `Assets/Scripts/...`.

## Steps
1. **Register first.** Every tunable number is an entry in `Assets/Content/<Pack>/Register/*.json`:
   ```json
   { "registerVersion": 1,
     "sources": [ { "key": "src.x", "title": "...", "author": "...", "date": "...", "url": "", "accessNote": "" } ],
     "entries": [ { "key": "plc.mbt.a.mass", "quantity": "mass", "unit": "t", "value": 46,
                    "evidence": "GameplayApproximation", "confidence": "Estimated" } ] }
   ```
   - `quantity` and `unit` come from the closed vocabulary in `RegisterVocabulary` (mass kg/t/g, length m/km/mm, range m/km, speed m/s and km/h, penetration_rha mm); the bake converts to the base unit once. Add a quantity there (with a test) before using a new one.
   - A **table** value is `[[x, y], ...]` with strictly ascending x and needs `"xQuantity"` and `"xUnit"` matching the vocabulary (`penetration_rha`: `range`, `m`); only table quantities may be tables.
   - Placeholders: keys under `plc.` must be `GameplayApproximation` / `Estimated`. Anything else needs `sources` (keys of entries in a `sources` array). Never present an unsupported coefficient as validated equipment data (`docs/research/physics_research_audit.md`).
   - Files are LF text (`.gitattributes` enforces it). Register keys are unique across all packs.
2. **Create the definition** as a ScriptableObject deriving from `DefinitionAsset` (`Family`, `Validate(ValidationContext)`, `Bake(BakeContext)`); physical fields are `RegisterValueField` (`RegisterValueField.ToRegister("key")`, or a local value with a unit, only as GameplayApproximation). In `Bake` resolve every field with `ctx.TryResolveRegister(name, field, quantity, out value)` and other definitions with `ctx.TryResolveDefinition`. Variants use `m_VariantOf` + `m_Overrides` (top-level field names of the family); never copy an asset.
3. **Licence entry:** any external art/audio/data gets a licence record (delivery plan section 7.2); original placeholder content records "original".
4. **Validate:** menu *Trishul / Validate All Content* (`ContentValidationMenu`, logs every finding and the `ContentHash`), or the EditMode test via skill `tte-unity-test`: `-TestFilter "Trishul.Tests.EditMode.Content.AllContentValidatesTests"` (`AllContentValidates` bakes `Assets/Content` and bakes twice for equal hashes). Programmatically: `ContentProject.TryBake("Assets/Content", ctx, out BakedContent content)`.
5. **Commit** the asset **with its `.meta`** (never let two assets share a GUID); stage by explicit path.
6. A new key, rename, removed key or changed register value changes `ContentHash` (a register entry no definition references changes only `RegisterHash`) and may change goldens: list it in the phase red list and tell the orchestrator. Replays and checkpoints record the `ContentHash` of their battle (`BakedBattle.ContentHash`, `BattleSetupReport`, `ReplayStartRecord`, `Units.State`).

---
name: tte-asset-pipeline
description: Take an external art asset (vehicle model or map heightmap) from TTE requirements through the staged-delivery check to a bound, tested TTE import. Covers publishing requirement copies to tte-art-staging, the per-family I1-I13 vehicle check and map probe check with verdict files, the import brief (Git LFS gate, importers, URP materials, LODGroup prefab via VehicleViewPrefabBuilder, ViewBinding, licence record, tests, screenshots), the playable checklist, and known pitfalls. Designer role for requirements and checks; implementor role for the import.
---

# Asset pipeline (`tte-asset-pipeline`)

**Proven on:** the Leopard 2A5 (Kucher source): delivery check 2026-11-19, import PR 143 (merge `9a68ef45`). The M0 map heightmap: delivery check 2026-11-19 (import pending G03a.06).

**Boundary (owner, 2026-11-19).**
- TTE writes the requirements, checks the deliveries, and imports.
- Production stays with the owner on the `military_assets` side.
- **Never write into `E:\Projects\military_assets`**, and never dispatch Blender or production workers there.
- The only shared place is `E:\Projects\tte-art-staging\`. It is not a git repository.

**Sources of truth** (TTE `main`):
- `docs/design/art/vehicle_families/`:
  - `common.md`: shared rules; §11 is the I1–I13 check with the family source of each item; §12 is the T1–T6 playable path;
  - `mbt.md`, `tracked_ifv_apc.md`, `wheeled_apc_ifv.md`, `not_yet_needed.md`;
  - `model_sheet_template.md`.
- `docs/design/art/vehicle_art_spec.md`: rationale, the published-field map, contract requests, final acceptance §10. Precedence: family specs govern family items, and the spec governs shared rules.
- `docs/design/art/asset_requirements_handoff.md`: the "start here" page and the asset priority list.
- `docs/design/art/m0_map_layout_spec.md`: the map example; §8 is the delivery check and §10 the probes.

---

## Stage 1: Requirements

1. **Write or change the spec** in TTE `docs/design/art/` as a docs-only PR from your own project worktree, cut from `origin/main`.
   - Put `[skip ci]` in the subject. The designer merges docs-only PRs without waiting for CI.
   - A new model in an existing family needs **no new spec**: the owner fills a model sheet.
   - Write a new spec only for a new family, a new asset kind (a map, say), or a deviation the family spec does not allow.
2. **Publish the staging copy from the merged blob, never from the worktree.** Worktree files may have CRLF line endings, so a copy from there changes the hash.

   ```bash
   R=E:/Projects/trishul-tactical-engine; M=<merge-sha>; S=E:/Projects/tte-art-staging/requirements
   export MSYS_NO_PATHCONV=1   # Git Bash otherwise mangles "<sha>:<path>"
   git -C $R show $M:docs/design/art/vehicle_families/common.md > $S/TTE_vehicle_common.md
   [ "$(git -C $R show $M:docs/design/art/vehicle_families/common.md | sha256sum)" = "$(sha256sum < $S/TTE_vehicle_common.md)" ]
   ```

   The copies are named `TTE_<topic>.md`. The current set is `TTE_asset_requirements.md`, `TTE_vehicle_common.md`, `TTE_family_{mbt,tracked_ifv_apc,wheeled_apc_ifv,not_yet_needed}.md`, `TTE_model_sheet_template.md` and `TTE_m0_map_layout.md`.
3. **Record the README commit row** in `E:\Projects\tte-art-staging\README.md` (`| requirements/<file> | <TTE source path> | <short sha> |`).
   - Add a row for each new file. Move the commit on refreshed rows, and leave the other rows alone.
   - Keep the README's existing line endings.
4. Tell the manager which staging files the owner should use. The owner passes them on; TTE sends nothing to `military_assets` itself.

---

## Stage 2: Delivery check (read-only, outside Unity)

A delivery arrives in `E:\Projects\tte-art-staging\<Key>\`. Run the check **read-only**: no edits in staging, no Unity, nothing in the TTE repository. If you use a checker worker, it is read-only too. Use whatever provider the manager names; when Codex or agy are low on budget, use a Claude subagent.

### 2a. Vehicle: I1–I13 per family (`common.md` §11)

| # | How to check | Family values |
|---|---|---|
| I1 | List the files. Re-import in headless Blender and walk the tree. Folder name exactly `<Key>`. `MODEL_SHEET.md` present. The declared scope (base: no `Damage_*` or wreck) | family §Hierarchy, the sheet's deviations |
| I2/I3 | Read `PROVENANCE.md`. Recompute the SHA-256 of reachable inputs and outputs. `aiToolUsed` is honest; the licence allows commercial use, modification and redistribution; nothing from `leopard-2-a6.zip`; no unapproved paid asset | **hard stop** on failure |
| I4 | Blender re-import, then convert the Blender axes to Unity. Contact patches at y = 0 ± 0.02 m | |
| I5 | Measure the named `Hull` and `Turret` meshes against the chassis row. Where the family has no row, use the sheet's published dimensions and the family range | family §Dimensions |
| I6 | Rotate the pivots in the re-imported scene: yaw ±90° and the family pitch range. The pivots agree across LODs within 1 mm | family §Station |
| I7 | Each socket under the right parent, with +Z along the effect | Common §6 plus the family table |
| I8 | Triangles and material slots per FBX and LOD. Each step at least halves the count | family §Budgets |
| I9 | Collision proxy: ≤ 200 triangles, the exact names, no material | |
| I10 | Pillow: size, mode and channel statistics. Mask B = 0. Spot-check one raised feature for OpenGL +Y normals. No embedded textures | |
| I11 | Judge the 150 m and 400 m renders against the family's silhouette list | family §Silhouette |
| I12 | `DELIVERY.md` has every Common §9 item | |
| I13 | `du` of the FBX and PNG files (Git LFS quota) | note only |

### 2b. Map: probe check (`m0_map_layout_spec.md` §8 and §10)

1. Check the RAW byte size (513 × 513 × 2, no header).
2. Decode it (uint16 little-endian; row 0 = south). Every sample must be within 2 cm of the spec's height formula. Also prove the orientation: the flipped reading must fail by metres.
3. Compare the probe CSV with the §10 table (±0.15 m).
4. Check the mask: size, strictly one-hot, top row = north, and the regions in the right places.
5. Rerun the sightlines and slopes through a simulation of the H1 bake chain (resample to 1 m, quantise to 1 cm, bilinear), and compare with the spec's expected exposures.
6. Check that the PROVENANCE hashes match the delivered files.

The formula and bake-chain tools are in `.local/handoffs/designer/m0map_tools/` (`m0map.py`, `m0bake.py`; this folder is not tracked). Run them with an explicit `sys.path` insert; `python -I` drops the script directory.

### 2c. Verdict file

Write `.local/handoffs/designer/verdict_<Key>_<YYYY-MM-DD>.md` with:
- a **PASS** or **numbered fix list** line first;
- a table of every check with its result and **your own measured evidence** (never the producer's numbers restated);
- non-blocking notes (naming deviations, stray files, accepted readings of ambiguous spec text);
- what you did **not** verify.

Send the manager the verdict in a few lines plus the file path. **The import starts only from a PASS.**

---

## Stage 3: Import (an implementor job in the shared Unity slot)

The orchestrator dispatches the import brief when the Unity slot is free (enforced via `unity-pipeline`'s `OSLock`). The worker pushes nothing until the LFS gate passes. Steps, in the order PR 143 used:

0. **Git LFS** (already on `main` since PR 143). `.gitattributes` tracks `*.fbx *.FBX *.png *.PNG *.tga *.psd *.exr`, and `unity-ci.yml` checks out with `lfs: true` on the EditMode and PlayMode jobs.
   - **The gate before the first push:** `git lfs version`, then `git lfs ls-files` lists every FBX and PNG, then `git show HEAD:<one fbx>` shows a pointer (`version https://git-lfs…`).
   - Push with `timeout 300` and the gh credential helper.
1. **Copy only the FBX and PNG files** into `Assets/Content/<Pack>/Art/Vehicles/<Key>/{Models,Textures}`. Staging may keep the FBX files at the folder root; the TTE layout is fixed.
   - Never copy `.prefab`, `.mat`, `.asset`, `.meta`, `.blend`, renders or notes. `military_assets` runs another editor version.
2. **Importers** (set by the builder):
   - models: scale 1, materials None, Read/Write off, no animation, rig or cameras, Bake Axis Conversion off. The builder asserts identity roots and skips socket nodes;
   - textures: BaseColor sRGB; Mask linear with alpha from input; Normal as a normal map with no green flip; max size 2048 for Body and Burnt, 1024 for Running.
3. **URP Lit materials** `<Key>_Body`, `_Running`, `_Burnt` (metallic workflow):
   - Base and Normal maps;
   - **the Mask in both the Metallic and the Occlusion slots**;
   - Smoothness Source = Metallic Alpha;
   - keywords `_NORMALMAP`, `_METALLICSPECGLOSSMAP`, `_OCCLUSIONMAP`.
4. **Prefabs via `Assets/Scripts/Trishul/Authoring/Editor/VehicleViewPrefabBuilder.cs`.**
   - Add a `VehicleSpec` for the new key: folder, LOD count, LOD heights, texture sizes, material rules derived from the FBX material descriptions, and the wreck LODs.
   - Add a menu item and a batch entry, modelled on `BuildLeopard2A5Menu` and `BuildLeopard2A5Batch`.
   - The view prefab gets:
     - a LODGroup; the defaults are 0.6 / 0.3 / 0.1 / 0.01;
     - **one** `Turret_Pivot` at the ring, with **one** `Gun_Elevation_Pivot` under it;
     - each LOD's station parts re-parented under those pivots;
     - the collision proxy's own `Turret_Pivot` renamed `Collision_Turret_Pivot`, with convex MeshColliders and no renderers;
     - LOD1–3 sockets removed;
     - `Damage_*` set inactive.
   - The wreck prefab is unbound: 2 LODs, all `<Key>_Burnt`.
   - The builder throws on a stop condition (axis, size, pivot disagreement, sub-mesh mismatch, a missing rule). **Report a stop; never work around it.**
   - The root fileID survives a re-run, so the binding stays valid. Child fileIDs change on every run; prefabs are structurally identical, not byte-identical.
5. **ViewBinding** (`Assets/Content/Core/Presentation/ViewBinding.asset`): add an own-vehicle entry `{VariantKey: <baked archetype key>, Prefab: <Key>_View}`.
   - The key is the variant's content key (for example `plc.mbt.b`), never an asset name.
   - The asset is referenced by `m_ViewBinding` in `M0-TankSkirmish.unity` and `ScenarioBootstrap.unity`.
6. **Licence record** in `Data/AssetLicenses/<pack>.json`, copied from `PROVENANCE.md`. Leave `url` blank when there is none.
   - A folder record is allowed only when the folder holds one source.
   - Check: `python ci/asset_licence_lint.py` gives 0 unregistered.
7. **Tests:**
   - EditMode prefab shape: one pivot pair; the LOD count; the `Damage_*` count, all inactive; proxy-only convex colliders;
   - chassis LOD0 bounds (length and width, min y 0) and muzzle z > 3 under the gun pivot;
   - the wreck's LODs and material;
   - binding resolution, and the scene references;
   - PlayMode: every playable force in turn; only the bound force shows `<Key>_View(Clone)`, at identity transform with its colliders disabled; the root selection BoxCollider stays enabled.
   - Register a new EditMode file in `ci/DotnetTests/excluded-files.txt` (reason `unity-engine-api`).
   - Run the full suites locally with `!Heavy;!P17FocusedLongActivity` and diff per test against the base commit's CI XML.
   - **No golden, pin or hash movement**, and no Runtime or Contracts changes.
8. **Screenshots** at 1600 × 900 (from a temporary helper, not committed):
   - the tactical camera start pose;
   - a close-up, and a close-up without the own-unit tint;
   - about 85 m out.

   The designer judges size and look before merge.
9. **Revert Unity's incidental edits** to `ProjectSettings/*`, `UniversalRenderPipelineGlobalSettings.asset` and scene materials. Leave untracked folder `.meta` files alone.

**Merge:** the manager merges on green CI plus a PASS review. The reviewer must be from another model family; if it is not, the PR body says why.

---

## Stage 4: Playable checklist (`common.md` §12)

| # | Needed before the model shows in play | Status to state |
|---|---|---|
| T1 | Import (Stage 3) | PR |
| T2 | Chassis rows: generic `plc.chassis.mbt` today; per-vehicle rows through B06 from published sources; no IFV chassis until M3; no wheeled chassis | the row key, or "waits on <phase>" |
| T3 | Weapon station and variant archetype under a content key | the key |
| T4 | ViewBinding entry | done or not |
| T5 | A mission or force setup that fields the variant | the mission |
| T6 | Tests plus the designer's screenshot judgement | the verdict |

Contact models (how enemies look) can be bound in ViewBinding, but the scenario still draws contacts as markers. Showing them needs a presentation change first.

---

## Known pitfalls

- **`Damage_*` scoping.** The builder deactivates `Damage_*` only under the chassis and station hierarchies. The prefix must never appear on non-damage objects, or in wreck, collision or kit files. A damage mesh left active doubles the geometry, and inactive damage meshes must be excluded from bounds (the inactive `Damage_Track_*` extend the Leopard's z).
- **Folder-name deviations.** Staging folders must be named exactly `<Key>`: `Map_M0` arrived for a spec that said `M0Map`, and the Leopard build ran under `Leopard2A4_*` names. A name deviation is recorded in the verdict. It blocks only if something on the TTE side reads the name, and every file, object and material name inside must still match the key.
- **CRLF hashes.** Hash text files over the bytes as staged. A git checkout with autocrlf, or a copy from a worktree, changes them. Publish staging copies with `git show <sha>:<path>`. When a PROVENANCE hash fails only on a text file, check the line endings before calling it tampering.
- **Stray files** (for example a duplicate image dropped by a generator). Note them in the verdict; they are never imported.
- **Hard-coded size check.** `VehicleViewPrefabBuilder.BuildViewPrefab` asserts the Leopard's 7.74 × 3.75 m chassis. The next vehicle's import must move the expected length and width (and their tolerance) into `VehicleSpec`.
- **Builder limits.** It assumes a station on every vehicle; an unarmed APC needs a builder change. The wheeled `Steer_*` and `Wheel_*` hierarchy and wheeled material rules are new too.
- **The metallic slider does nothing.** URP Lit ignores `_Metallic` while a Metallic map is set. Too much sheen is fixed in the mask's R channel on the producer side, never in a code workaround.
- **The own-unit tint.** `DemoSelectionTint` multiplies BaseColor blue on every own view, which hides textured camouflage. The replacement is specified in `.local/handoffs/designer/spec_unit_marker_2026-11-19.md` (its own batch). Judge the look from an untinted close-up.
- **`Find("Turret")`.** The bootstrap's turret driver looks for a direct child named `Turret`, which bound prefabs do not have. The turret stays at rest until the presentation drives `Turret_Pivot`.
- **The selection collider** is still 2.2 × 3.4 m against real hulls (a follow-up batch).
- **Git Bash.** `MSYS_NO_PATHCONV=1` for `git show <sha>:<path>`. `git -C <worktree>` with `set -e` in scripts. Push with `timeout 60 git -c credential.helper= -c credential.helper='!gh auth git-credential' push …` (`timeout 300` for an LFS push).
- **No AI attribution** in commits or PRs.

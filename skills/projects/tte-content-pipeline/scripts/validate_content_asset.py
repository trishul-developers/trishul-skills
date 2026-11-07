#!/usr/bin/env python3
r"""Content Asset & Register Validator for Trishul Tactical Engine (TTE).

Performs offline linting and validation without needing to launch Unity:
  - Validates key syntax [a-z0-9._-] (dot-separated non-empty segments, max 96 chars)
  - Computes 32-bit FNV-1a DefinitionId and checks for hash collisions
  - Validates register JSON quantities and units against RegisterVocabulary
  - Enforces placeholder rules (plc.* must be GameplayApproximation / Estimated)
  - Checks table monotonic ascending x-values
  - Audits cross-pack register key uniqueness across Assets/Content/
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# Closed Register Vocabulary from Trishul.Runtime.Content.RegisterVocabulary
REGISTER_VOCABULARY = {
    "mass": {"base_unit": "kg", "units": {"kg", "t", "g"}, "is_table": False},
    "length": {"base_unit": "m", "units": {"m", "km", "mm"}, "is_table": False},
    "range": {"base_unit": "m", "units": {"m", "km"}, "is_table": False},
    "speed": {"base_unit": "m/s", "units": {"m/s", "km/h"}, "is_table": False},
    "penetration_rha": {"base_unit": "mm", "units": {"mm"}, "is_table": True, "x_quantity": "range", "x_unit": "m"},
    "time": {"base_unit": "s", "units": {"s", "ms"}, "is_table": False},
    "angle": {"base_unit": "rad", "units": {"rad", "deg"}, "is_table": False},
    "angular_speed": {"base_unit": "rad/s", "units": {"rad/s", "deg/s"}, "is_table": False},
    "ratio": {"base_unit": "1", "units": {"1"}, "is_table": False},
    "count": {"base_unit": "1", "units": {"1"}, "is_table": False},
    "area": {"base_unit": "m2", "units": {"m2"}, "is_table": False},
    "damage_points": {"base_unit": "dp", "units": {"dp"}, "is_table": False},
}

MAX_KEY_LENGTH = 96
FNV_OFFSET_BASIS = 2166136261
FNV_PRIME = 16777619


def is_valid_key(key: str) -> bool:
    """True for a well-formed key: 1..96 ASCII characters in dot-separated non-empty segments."""
    if not key or len(key) > MAX_KEY_LENGTH:
        return False
    if key.startswith(".") or key.endswith("."):
        return False
    segments = key.split(".")
    for seg in segments:
        if not seg:
            return False
        if not re.fullmatch(r"[a-z0-9_-]+", seg):
            return False
    return True


def fnv1a_32(key: str) -> int:
    """32-bit FNV-1a hash of UTF-8 key bytes (never zero; maps 0 to 1)."""
    h = FNV_OFFSET_BASIS
    for b in key.encode("utf-8"):
        h ^= b
        h = (h * FNV_PRIME) & 0xFFFFFFFF
    return 1 if h == 0 else h


def validate_register_entry(entry: Dict[str, Any], known_sources: Set[str]) -> List[str]:
    """Validate a single register JSON entry."""
    errors = []
    key = entry.get("key")
    if not key:
        return ["Entry missing 'key' field."]

    if not is_valid_key(key):
        errors.append(f"Key '{key}' is invalid. Must be [a-z0-9._-] with non-empty dot segments, max {MAX_KEY_LENGTH} chars.")

    quantity = entry.get("quantity")
    if not quantity:
        errors.append(f"Key '{key}' missing 'quantity'.")
    elif quantity not in REGISTER_VOCABULARY:
        errors.append(f"Key '{key}' uses unknown quantity '{quantity}'. Allowed: {sorted(REGISTER_VOCABULARY.keys())}")
    else:
        q_def = REGISTER_VOCABULARY[quantity]
        unit = entry.get("unit")
        if not unit:
            errors.append(f"Key '{key}' missing 'unit'.")
        elif unit not in q_def["units"]:
            errors.append(f"Key '{key}' unit '{unit}' not valid for quantity '{quantity}'. Allowed: {sorted(q_def['units'])}")

        value = entry.get("value")
        if q_def["is_table"]:
            if not isinstance(value, list) or not all(isinstance(row, list) and len(row) == 2 for row in value):
                errors.append(f"Key '{key}' is table quantity '{quantity}'; value must be a list of [x, y] pairs.")
            else:
                x_vals = [row[0] for row in value]
                if any(x_vals[i] >= x_vals[i+1] for i in range(len(x_vals)-1)):
                    errors.append(f"Key '{key}' table x values must be strictly ascending: {x_vals}")

            x_qty = entry.get("xQuantity")
            x_unit = entry.get("xUnit")
            if x_qty != q_def["x_quantity"]:
                errors.append(f"Key '{key}' table requires xQuantity='{q_def['x_quantity']}', found '{x_qty}'.")
            if x_unit != q_def["x_unit"]:
                errors.append(f"Key '{key}' table requires xUnit='{q_def['x_unit']}', found '{x_unit}'.")
        else:
            if isinstance(value, list):
                errors.append(f"Key '{key}' is scalar quantity '{quantity}' but has table list value.")

    # Placeholder rules
    if key.startswith("plc."):
        if entry.get("evidence") != "GameplayApproximation":
            errors.append(f"Placeholder key '{key}' must have evidence: 'GameplayApproximation'.")
        if entry.get("confidence") != "Estimated":
            errors.append(f"Placeholder key '{key}' must have confidence: 'Estimated'.")
    else:
        sources = entry.get("sources")
        if not sources and entry.get("evidence") != "GameplayApproximation":
            errors.append(f"Production key '{key}' must reference at least one source key or be GameplayApproximation.")
        elif sources:
            for s in sources:
                if s not in known_sources:
                    errors.append(f"Key '{key}' cites source '{s}' which is not defined in the 'sources' array.")

    return errors


def audit_register_file(path: Path) -> Tuple[List[str], List[Tuple[str, int]]]:
    errors = []
    key_hashes = []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"Failed to parse JSON in {path}: {e}"], []

    if data.get("registerVersion") != 1:
        errors.append(f"{path}: 'registerVersion' must be 1.")

    sources_arr = data.get("sources", [])
    known_sources = {s.get("key") for s in sources_arr if isinstance(s, dict) and s.get("key")}

    entries = data.get("entries", [])
    if not isinstance(entries, list):
        errors.append(f"{path}: 'entries' must be a list.")
        return errors, []

    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"{path}: entry is not a dict: {entry}")
            continue
        entry_errors = validate_register_entry(entry, known_sources)
        for err in entry_errors:
            errors.append(f"{path.name} -> {err}")

        k = entry.get("key")
        if k and is_valid_key(k):
            key_hashes.append((k, fnv1a_32(k)))

    return errors, key_hashes


def audit_content_tree(content_dir: Path) -> int:
    print(f"Scanning Content tree at {content_dir}...")
    all_errors = []
    seen_keys: Dict[str, Path] = {}
    seen_hashes: Dict[int, Tuple[str, Path]] = {}

    register_files = list(content_dir.glob("**/Register/*.json"))
    if not register_files:
        print(f"Warning: No register JSON files found under {content_dir}")
        return 0

    print(f"Found {len(register_files)} register JSON file(s).")

    for rf in sorted(register_files):
        errs, key_hashes = audit_register_file(rf)
        all_errors.extend(errs)

        for key, h in key_hashes:
            # Check key collision across packs
            if key in seen_keys:
                all_errors.append(f"DUPLICATE KEY: '{key}' appears in both {seen_keys[key]} and {rf}")
            else:
                seen_keys[key] = rf

            # Check 32-bit FNV-1a collision
            if h in seen_hashes:
                other_key, other_file = seen_hashes[h]
                if other_key != key:
                    all_errors.append(f"FNV-1a HASH COLLISION (0x{h:08x}): '{key}' in {rf} collides with '{other_key}' in {other_file}")
            else:
                seen_hashes[h] = (key, rf)

    print(f"\nAudit Results:")
    print(f"  - Register files scanned: {len(register_files)}")
    print(f"  - Total unique keys: {len(seen_keys)}")
    print(f"  - Total DefinitionId hashes: {len(seen_hashes)}")
    print(f"  - Errors / Invariant Violations: {len(all_errors)}")

    if all_errors:
        print("\nErrors:")
        for err in all_errors:
            print(f"  [ERROR] {err}")
        return 1

    print("\nAll register files, keys, and DefinitionIds are 100% valid and collision-free!")
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="TTE Content Asset & Register Validator")
    parser.add_argument("--key", help="Compute 32-bit FNV-1a DefinitionId for a single key")
    parser.add_argument("--file", help="Validate a single candidate register JSON file")
    parser.add_argument("-C", "--content-dir", default="Assets/Content", help="Path to Assets/Content directory")
    args = parser.parse_args()

    if args.key:
        valid = is_valid_key(args.key)
        h = fnv1a_32(args.key)
        print(f"Key:          {args.key}")
        print(f"Well-formed:  {valid}")
        print(f"DefinitionId: {h} (0x{h:08x})")
        sys.exit(0 if valid else 1)

    if args.file:
        p = Path(args.file).resolve()
        if not p.exists():
            print(f"Error: {p} does not exist.", file=sys.stderr)
            sys.exit(1)
        errs, key_hashes = audit_register_file(p)
        print(f"Validating {p.name}: {len(key_hashes)} keys found, {len(errs)} error(s).")
        for k, h in key_hashes:
            print(f"  {k:35} -> 0x{h:08x} ({h})")
        if errs:
            for e in errs:
                print(f"  [ERROR] {e}")
            sys.exit(1)
        print("File is valid!")
        sys.exit(0)

    content_dir = Path(args.content_dir).resolve()
    if not content_dir.exists():
        # Check if run from repository root or skills root
        alt = Path("E:/Projects/trishul-tactical-engine/Assets/Content")
        if alt.exists():
            content_dir = alt
        else:
            print(f"Error: Content directory {content_dir} does not exist.", file=sys.stderr)
            sys.exit(1)

    sys.exit(audit_content_tree(content_dir))


if __name__ == "__main__":
    main()

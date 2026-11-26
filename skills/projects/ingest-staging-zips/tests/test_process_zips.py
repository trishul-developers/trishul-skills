import hashlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import process_zips  # noqa: E402


def _make_zip(zip_path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


class TestProcessZips(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_derive_key_tte_staging_and_single_root(self):
        z1 = self.root / "T72B3_TTE_Staging.zip"
        _make_zip(z1, {"T72B3/MODEL_SHEET.md": b"ok"})
        self.assertEqual(process_zips.derive_key(z1), "T72B3")

        z2 = self.root / "kit_bundle_v1.zip"
        _make_zip(z2, {"DesertKit/DELIVERY.md": b"ok", "DesertKit/Models/a.fbx": b"fbx"})
        self.assertEqual(process_zips.derive_key(z2), "DesertKit")

    def test_verify_checksums_file(self):
        asset_dir = self.root / "DesertKit"
        (asset_dir / "Models").mkdir(parents=True)
        fbx = asset_dir / "Models" / "rock.fbx"
        fbx.write_bytes(b"fbx-bytes")
        digest = hashlib.sha256(b"fbx-bytes").hexdigest()
        (asset_dir / "CHECKSUMS.sha256").write_text(f"{digest}  Models/rock.fbx\n", encoding="utf-8")

        checked, mismatches = process_zips.verify_checksums_file(asset_dir)
        self.assertEqual(checked, 1)
        self.assertEqual(mismatches, [])

    def test_process_zip_kit_pack_atomic(self):
        zips_dir = self.root / "zips"
        staging_root = self.root / "staging"
        military_root = self.root / "military"
        zips_dir.mkdir()

        fbx_bytes = b"kit-fbx"
        png_bytes = b"kit-png"
        csum = (
            f"{hashlib.sha256(fbx_bytes).hexdigest()}  Models/tree.fbx\n"
            f"{hashlib.sha256(png_bytes).hexdigest()}  Textures/tree.png\n"
        ).encode("utf-8")

        zpath = zips_dir / "FoliageKit_TTE_Staging.zip"
        _make_zip(
            zpath,
            {
                "FoliageKit/DELIVERY.md": b"ok",
                "FoliageKit/PROVENANCE.md": b"ok",
                "FoliageKit/MANIFEST.json": b"{}",
                "FoliageKit/CHECKSUMS.sha256": csum,
                "FoliageKit/Models/tree.fbx": fbx_bytes,
                "FoliageKit/Textures/tree.png": png_bytes,
                "FoliageKit/Evidence/view.png": b"ev",
            },
        )

        issues = process_zips.process_zip(
            zpath,
            staging_root=staging_root,
            military_root=military_root,
            keep_renders_in_staging=True,
            dry_run=False,
        )
        self.assertEqual(issues, [])
        self.assertTrue((staging_root / "FoliageKit" / "Models" / "tree.fbx").is_file())
        self.assertTrue((military_root / "Exports" / "FoliageKit" / "Models" / "tree.fbx").is_file())
        self.assertTrue((military_root / "Docs" / "AssetPreviews" / "FoliageKit" / "view.png").is_file())

    def test_dry_run_missing_staging_root_does_not_crash(self):
        zips_dir = self.root / "zips"
        zips_dir.mkdir()
        _make_zip(zips_dir / "Prop_Box_TTE_Staging.zip", {"Prop_Box/DELIVERY.md": b"ok"})

        missing_staging = self.root / "nonexistent_staging"
        res = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "process_zips.py"),
                "--zips-dir",
                str(zips_dir),
                "--staging-root",
                str(missing_staging),
                "--military-assets-root",
                str(self.root / "mil"),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("[DRY-RUN] Prop_Box", res.stdout)
        self.assertFalse(missing_staging.exists())


if __name__ == "__main__":
    unittest.main()

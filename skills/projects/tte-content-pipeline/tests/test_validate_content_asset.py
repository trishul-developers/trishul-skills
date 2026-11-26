import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_content_asset as vca  # noqa: E402


class TestValidateContentAsset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_requires_evidence_and_confidence_on_all_entries(self):
        entry = {
            "key": "mbt.t72b3.mass",
            "quantity": "mass",
            "unit": "t",
            "value": 46.5,
            "sources": ["src.manual"],
        }
        errs = vca.validate_register_entry(entry, {"src.manual"})
        self.assertTrue(any("evidence" in e for e in errs))
        self.assertTrue(any("confidence" in e for e in errs))

    def test_rejects_xquantity_xunit_on_scalar_entries(self):
        entry = {
            "key": "plc.mbt.a.mass",
            "quantity": "mass",
            "unit": "t",
            "value": 45,
            "xQuantity": "range",
            "xUnit": "m",
            "evidence": "GameplayApproximation",
            "confidence": "Estimated",
        }
        errs = vca.validate_register_entry(entry, set())
        self.assertTrue(any("xQuantity/xUnit" in e for e in errs))

        pen_scalar = {
            "key": "plc.gun.pen",
            "quantity": "penetration_rha",
            "unit": "mm",
            "value": 500,
            "xQuantity": "range",
            "xUnit": "m",
            "evidence": "GameplayApproximation",
            "confidence": "Estimated",
        }
        errs2 = vca.validate_register_entry(pen_scalar, set())
        self.assertTrue(any("xQuantity/xUnit" in e for e in errs2))

    def test_audit_register_file_validates_root_sources_entries(self):
        bad_root = self.root / "bad_root.json"
        bad_root.write_text("[]", encoding="utf-8")
        errs, _ = vca.audit_register_file(bad_root)
        self.assertTrue(any("root JSON must be an object" in e for e in errs))

        bad_shape = self.root / "bad_shape.json"
        bad_shape.write_text(json.dumps({"registerVersion": 1, "sources": "nope"}), encoding="utf-8")
        errs2, _ = vca.audit_register_file(bad_shape)
        self.assertTrue(any("'sources' must be a list" in e for e in errs2))
        self.assertTrue(any("'entries' must be a list" in e for e in errs2))

    def test_audit_content_tree_returns_nonzero_when_empty(self):
        empty_dir = self.root / "EmptyContent"
        empty_dir.mkdir()
        self.assertEqual(vca.audit_content_tree(empty_dir), 1)


if __name__ == "__main__":
    unittest.main()

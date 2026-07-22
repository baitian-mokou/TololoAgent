import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_esa_shadow_package.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apply_esa_shadow_package", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApplyEsaShadowPackageTests(unittest.TestCase):
    def make_package(self, root: Path, item_count: int = 18) -> tuple[Path, Path]:
        package = root / "evaluation" / "four_source_expansion" / "esa_package"
        package.mkdir(parents=True)
        (package / "triples_preview.json").write_text(json.dumps([{"subject": "Rosetta"}] * 70), encoding="utf-8")
        (package / "narratives_preview.json").write_text(json.dumps([{"content": "Rosetta mission"}] * 71), encoding="utf-8")
        (package / "package_manifest.json").write_text(json.dumps({"source_id": "esa", "items": item_count}), encoding="utf-8")
        approval = root / "evaluation" / "four_source_expansion" / "approval.json"
        approval.write_text(json.dumps({"source_id": "esa", "approval_decision": "pending", "approved_item_count": 0}), encoding="utf-8")
        return package, approval

    def test_pending_approval_rejected_without_writing(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, approval = self.make_package(root)
            out_dir = root / "data" / "triples_shadow" / "esa"
            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=out_dir, execute=True)
            self.assertFalse(report["allowed"])
            self.assertEqual(report["blocked_reason"], "approval_not_approved")
            self.assertFalse(out_dir.exists())

    def test_partial_approval_rejected(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, approval = self.make_package(root)
            approval.write_text(json.dumps({"source_id": "esa", "approval_decision": "approved_for_shadow_write", "approved_item_count": 17}), encoding="utf-8")
            out_dir = root / "data" / "triples_shadow" / "esa"
            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=out_dir, execute=True)
            self.assertFalse(report["allowed"])
            self.assertEqual(report["blocked_reason"], "approved_item_count_mismatch")
            self.assertFalse(out_dir.exists())

    def test_rejects_non_fixed_shadow_path(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, approval = self.make_package(root)
            approval.write_text(json.dumps({"source_id": "esa", "approval_decision": "approved_for_shadow_write", "approved_item_count": 18}), encoding="utf-8")
            out_dir = root / "data" / "triples" / "esa_shadow"
            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=out_dir, execute=True)
            self.assertFalse(report["allowed"])
            self.assertEqual(report["blocked_reason"], "output_not_shadow_only")
            self.assertFalse(out_dir.exists())

    def test_approved_execute_writes_only_fixed_shadow_path(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, approval = self.make_package(root)
            approval.write_text(json.dumps({"source_id": "esa", "approval_decision": "approved_for_shadow_write", "approved_item_count": 18}), encoding="utf-8")
            out_dir = root / "data" / "triples_shadow" / "esa"
            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=out_dir, execute=True)
            self.assertTrue(report["allowed"])
            self.assertTrue(report["executed"])
            self.assertTrue((out_dir / "triples_preview.json").exists())
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())

    def test_script_has_no_chroma_neo4j_or_active_source_mutation(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("ChromaStore", source)
        self.assertNotIn("Neo4jLoader", source)
        self.assertIsNone(re.search(r"^ACTIVE_SOURCE\s*=", source, flags=re.M))
        self.assertNotIn("clear_source_ingestion_outputs", source)


if __name__ == "__main__":
    unittest.main()

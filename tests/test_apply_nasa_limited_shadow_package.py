import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_nasa_limited_shadow_package.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apply_nasa_limited_shadow_package", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApplyNasaLimitedShadowPackageTests(unittest.TestCase):
    def make_package(self, root: Path) -> tuple[Path, Path]:
        package = root / "evaluation" / "four_source_expansion" / "package"
        package.mkdir(parents=True)
        (package / "triples_preview.json").write_text(
            json.dumps([{"subject": "Apophis", "predicate": "INSTANCE_OF", "object": "asteroid", "evidence": "Apophis is an asteroid.", "confidence": 0.82}]),
            encoding="utf-8",
        )
        (package / "narratives_preview.json").write_text(
            json.dumps([{"content": "Apophis is a near-Earth asteroid.", "source_id": "nasa"}]),
            encoding="utf-8",
        )
        approval = root / "evaluation" / "four_source_expansion" / "approval.json"
        approval.write_text(json.dumps({"source_id": "nasa", "approval_decision": "pending", "approved_item_count": 0}), encoding="utf-8")
        return package, approval

    def test_pending_approval_is_rejected_before_writing(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, approval = self.make_package(root)
            out_dir = root / "data" / "triples_shadow" / "nasa"

            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=out_dir, execute=True)

            self.assertFalse(report["allowed"])
            self.assertEqual(report["blocked_reason"], "approval_not_approved")
            self.assertFalse(out_dir.exists())

    def test_rejects_default_triples_output_even_when_approved(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, approval = self.make_package(root)
            approval.write_text(json.dumps({"source_id": "nasa", "approval_decision": "approved_for_shadow_write", "approved_item_count": 1}), encoding="utf-8")

            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=root / "data" / "triples" / "nasa", execute=True)

            self.assertFalse(report["allowed"])
            self.assertEqual(report["blocked_reason"], "output_not_shadow_only")
            self.assertFalse((root / "data" / "triples" / "nasa").exists())

    def test_approved_execute_writes_only_shadow_output(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, approval = self.make_package(root)
            approval.write_text(json.dumps({"source_id": "nasa", "approval_decision": "approved_for_shadow_write", "approved_item_count": 1}), encoding="utf-8")
            out_dir = root / "data" / "triples_shadow" / "nasa"

            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=out_dir, execute=True)

            self.assertTrue(report["allowed"])
            self.assertTrue(report["executed"])
            self.assertTrue((out_dir / "triples_preview.json").exists())
            self.assertTrue((out_dir / "narratives_preview.json").exists())
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())

    def test_dry_run_with_approval_does_not_write(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, approval = self.make_package(root)
            approval.write_text(json.dumps({"source_id": "nasa", "approval_decision": "approved_for_shadow_write", "approved_item_count": 1}), encoding="utf-8")
            out_dir = root / "data" / "triples_shadow" / "nasa"

            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=out_dir, execute=False)

            self.assertTrue(report["allowed"])
            self.assertFalse(report["executed"])
            self.assertFalse(out_dir.exists())

    def test_script_has_no_chroma_neo4j_or_active_source_mutation(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("ChromaStore", source)
        self.assertNotIn("Neo4jLoader", source)
        self.assertIsNone(re.search(r"^ACTIVE_SOURCE\s*=", source, flags=re.M))
        self.assertNotIn("clear_source_ingestion_outputs", source)


if __name__ == "__main__":
    unittest.main()

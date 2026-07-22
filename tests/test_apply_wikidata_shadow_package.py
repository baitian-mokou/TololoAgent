import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_wikidata_shadow_package.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apply_wikidata_shadow_package", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApplyWikidataShadowPackageTests(unittest.TestCase):
    def make_package(self, root: Path, item_count: int = 25, source_id: str = "wikidata") -> tuple[Path, Path]:
        package = root / "evaluation" / "four_source_expansion" / "wikidata_package"
        package.mkdir(parents=True)
        triple = {"subject": "火星", "predicate": "PART_OF", "object": "太阳系", "qid": "Q111", "source_id": source_id, "schema_version": "wikidata_shadow_ready_v1"}
        narrative = {"page_title": "火星", "content": "火星 narrative", "qid": "Q111", "source_id": source_id, "schema_version": "wikidata_shadow_ready_v1"}
        (package / "triples_preview.json").write_text(json.dumps([triple] * 151), encoding="utf-8")
        (package / "narratives_preview.json").write_text(json.dumps([narrative] * 25), encoding="utf-8")
        (package / "package_manifest.json").write_text(json.dumps({"source_id": source_id, "schema_version": "wikidata_shadow_ready_v1", "items": item_count}), encoding="utf-8")
        approval = root / "evaluation" / "four_source_expansion" / "approval.json"
        approval.write_text(json.dumps({"source_id": "wikidata", "approval_decision": "pending", "approved_item_count": 0}), encoding="utf-8")
        return package, approval

    def test_pending_approval_rejected_without_writing(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, approval = self.make_package(root)
            out_dir = root / "data" / "triples_shadow" / "wikidata"
            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=out_dir, execute=True)
            self.assertFalse(report["allowed"])
            self.assertEqual(report["blocked_reason"], "approval_not_approved")
            self.assertFalse(out_dir.exists())

    def test_partial_and_source_mismatch_rejected(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, approval = self.make_package(root)
            approval.write_text(json.dumps({"source_id": "wikidata", "approval_decision": "approved_for_shadow_write", "approved_item_count": 24}), encoding="utf-8")
            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=root / "data" / "triples_shadow" / "wikidata", execute=True)
            self.assertEqual(report["blocked_reason"], "approved_item_count_mismatch")
            approval.write_text(json.dumps({"source_id": "esa", "approval_decision": "approved_for_shadow_write", "approved_item_count": 25}), encoding="utf-8")
            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=root / "data" / "triples_shadow" / "wikidata", execute=True)
            self.assertEqual(report["blocked_reason"], "approval_source_mismatch")

    def test_rejects_non_fixed_shadow_path_and_bad_schema(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, approval = self.make_package(root)
            approval.write_text(json.dumps({"source_id": "wikidata", "approval_decision": "approved_for_shadow_write", "approved_item_count": 25}), encoding="utf-8")
            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=root / "data" / "triples" / "wikidata_shadow", execute=True)
            self.assertEqual(report["blocked_reason"], "output_not_shadow_only")
            bad_package, bad_approval = self.make_package(root / "bad", source_id="nasa")
            bad_approval.write_text(json.dumps({"source_id": "wikidata", "approval_decision": "approved_for_shadow_write", "approved_item_count": 25}), encoding="utf-8")
            report = module.build_apply_report(package_dir=bad_package, approval_path=bad_approval, shadow_output_dir=root / "bad" / "data" / "triples_shadow" / "wikidata", execute=True)
            self.assertEqual(report["blocked_reason"], "package_schema_invalid")

    def test_approved_execute_writes_only_fixed_shadow_path(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, approval = self.make_package(root)
            approval.write_text(json.dumps({"source_id": "wikidata", "approval_decision": "approved_for_shadow_write", "approved_item_count": 25}), encoding="utf-8")
            out_dir = root / "data" / "triples_shadow" / "wikidata"
            report = module.build_apply_report(package_dir=package, approval_path=approval, shadow_output_dir=out_dir, execute=True)
            self.assertTrue(report["allowed"])
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

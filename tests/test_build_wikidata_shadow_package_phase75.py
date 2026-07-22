import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_wikidata_shadow_package_phase75.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_wikidata_shadow_package_phase75", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildWikidataShadowPackagePhase75Tests(unittest.TestCase):
    def write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_builds_pending_package_from_raw(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw" / "Q1.json"
            self.write_json(raw, {"record": {"qid": "Q1", "title": "Mars", "triples": [{"relation": "PART_OF", "object": "Solar System"}], "narratives": [{"content": "Mars is in the Solar System."}]}})
            phase74 = root / "phase74.json"
            self.write_json(phase74, {"candidate_statuses": [{"status": "accepted_for_package", "qid": "Q1", "title": "Mars", "url": "https://www.wikidata.org/wiki/Q1", "raw_path": str(raw)}]})
            report = module.build_package(phase74_json=phase74, triples_root=root / "triples", out_dir=root / "evaluation" / "four_source_expansion" / "p75", approval_template=root / "evaluation" / "four_source_expansion" / "approval.json")
            self.assertEqual(report["packaged_items"], 1)
            self.assertEqual(report["approval_status"], "pending")
            triples = json.loads((root / "evaluation" / "four_source_expansion" / "p75" / "triples_preview.json").read_text())
            self.assertEqual(triples[0]["source_id"], "wikidata")
            self.assertEqual(triples[0]["schema_version"], "wikidata_shadow_ready_v1")
            self.assertFalse(report["formal_triples_write"])
            self.assertFalse((root / "data" / "chroma_db").exists())

    def test_review_needed_not_selected_and_materialized_pair_used(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            phase74 = root / "phase74.json"
            self.write_json(
                phase74,
                {"candidate_statuses": [
                    {"status": "accepted_for_package", "qid": "Q2", "title": "Earth", "url": "https://www.wikidata.org/wiki/Q2"},
                    {"status": "review_needed", "qid": "Q3", "title": "Bad", "url": "https://www.wikidata.org/wiki/Q3"},
                ]},
            )
            triples_root = root / "triples"
            self.write_json(triples_root / "Earth_triples.json", [{"subject": "Earth", "relation": "PART_OF", "object": "Solar System", "schema_version": "wikidata_shadow_ready_v1"}])
            self.write_json(triples_root / "Earth_narratives.json", [{"page_title": "Earth", "content": "Earth narrative.", "schema_version": "wikidata_shadow_ready_v1"}])
            report = module.build_package(phase74_json=phase74, triples_root=triples_root, out_dir=root / "evaluation" / "four_source_expansion" / "p75", approval_template=root / "evaluation" / "four_source_expansion" / "approval.json")
            self.assertEqual(report["selected_count"], 1)
            self.assertEqual(report["packaged_items"], 1)

    def test_internal_duplicate_qid_title_skipped_and_output_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_a = root / "raw" / "a.json"
            raw_b = root / "raw" / "b.json"
            self.write_json(raw_a, {"record": {"qid": "Q1", "title": "Mars", "triples": [{"relation": "PART_OF", "object": "Solar System"}], "narratives": [{"content": "Mars."}]}})
            self.write_json(raw_b, {"record": {"qid": "Q1", "title": "Mars", "triples": [{"relation": "PART_OF", "object": "Solar System"}], "narratives": [{"content": "Mars."}]}})
            phase74 = root / "phase74.json"
            self.write_json(phase74, {"candidate_statuses": [
                {"status": "accepted_for_package", "qid": "Q1", "title": "Mars", "url": "https://www.wikidata.org/wiki/Q1", "raw_path": str(raw_a)},
                {"status": "accepted_for_package", "qid": "Q1", "title": "Mars", "url": "https://www.wikidata.org/wiki/Q1", "raw_path": str(raw_b)},
            ]})
            report = module.build_package(phase74_json=phase74, triples_root=root / "triples", out_dir=root / "evaluation" / "four_source_expansion" / "p75", approval_template=root / "evaluation" / "four_source_expansion" / "approval.json")
            self.assertEqual(report["packaged_items"], 1)
            self.assertEqual(report["duplicate_skipped"], 1)
            self.assertTrue(module.output_allowed(ROOT / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertFalse(module.output_allowed(root / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

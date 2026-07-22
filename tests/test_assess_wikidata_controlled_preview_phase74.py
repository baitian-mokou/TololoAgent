import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "assess_wikidata_controlled_preview_phase74.py"


def load_module():
    spec = importlib.util.spec_from_file_location("assess_wikidata_controlled_preview_phase74", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AssessWikidataControlledPreviewPhase74Tests(unittest.TestCase):
    def write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_max_batch_disabled_and_no_formal_writes(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frontier = root / "evaluation" / "source_frontiers" / "wikidata_frontier.json"
            rows = [{"qid": f"Q{i}", "entity": f"Entity {i}", "url": f"https://www.wikidata.org/wiki/Q{i}"} for i in range(60)]
            self.write_json(frontier, {"accepted": rows})
            raw_root = root / "data" / "raw_json" / "wikidata"
            self.write_json(raw_root / "Q0.json", {"record": {"qid": "Q0", "title": "Entity 0", "triples": [{"relation": "INSTANCE_OF"}], "narratives": [{"content": "Entity 0"}]}})
            report = module.assess_wikidata(frontier_json=frontier, raw_root=raw_root, triples_root=root / "data" / "triples" / "wikidata", limit=99)
            self.assertEqual(report["selected"], 50)
            self.assertEqual(report["accepted_for_package"], 1)
            self.assertEqual(module.SOURCE_REGISTRY.get("wikidata"), "disabled")
            self.assertFalse(report["formal_triples_write"])
            self.assertFalse((root / "data" / "chroma_db").exists())

    def test_materialized_pair_counts_as_accepted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frontier = root / "frontier.json"
            self.write_json(frontier, {"accepted": [{"qid": "Q1", "entity": "Mars", "url": "https://www.wikidata.org/wiki/Q1"}]})
            triples_root = root / "data" / "triples" / "wikidata"
            self.write_json(triples_root / "Mars_triples.json", [{"subject": "Mars"}])
            self.write_json(triples_root / "Mars_narratives.json", [{"content": "Mars"}])
            report = module.assess_wikidata(frontier_json=frontier, raw_root=root / "raw", triples_root=triples_root)
            self.assertEqual(report["accepted_for_package"], 1)
            self.assertEqual(report["candidate_statuses"][0]["reason"], "local_materialized_preview_exists")

    def test_output_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            outside = Path(temp)
            self.assertTrue(module.output_allowed(ROOT / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(ROOT / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(outside / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

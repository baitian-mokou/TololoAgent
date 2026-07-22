import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preview_nasa_text_relation_extraction.py"


def load_module():
    spec = importlib.util.spec_from_file_location("preview_nasa_text_relation_extraction", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NasaTextRelationExtractionPreviewTests(unittest.TestCase):
    def test_extracts_conservative_nasa_text_relations_and_skips_other_sources(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            trial_dir = root / "evaluation" / "four_source_expansion" / "phase43"
            trial_dir.mkdir(parents=True)
            raw_path = root / "data" / "raw_json" / "nasa" / "apophis.json"
            raw_path.parent.mkdir(parents=True)
            raw_path.write_text(json.dumps({"title": "Apophis", "text": "Apophis is a near-Earth asteroid."}), encoding="utf-8")
            trial = {
                "trial": True,
                "source_id": "nasa",
                "raw_path": str(raw_path),
                "source_url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "title": "Apophis - NASA Science",
                "narratives": [{
                    "content": (
                        "Apophis is a near-Earth asteroid. Its diameter is about 340 meters. "
                        "Apophis was discovered by Roy Tucker. It is named after an Egyptian god. "
                        "Apophis will make a close approach to Earth in 2029."
                    )
                }],
            }
            (trial_dir / "apophis.json").write_text(json.dumps(trial), encoding="utf-8")
            phase42 = {
                "items": [
                    {"source_id": "nasa", "quality_triage": "accepted", "raw_path": str(raw_path)},
                    {"source_id": "esa", "quality_triage": "accepted", "raw_path": str(raw_path)},
                    {"source_id": "nasa", "quality_triage": "review_needed", "raw_path": str(raw_path)},
                ]
            }
            phase42_path = root / "evaluation" / "four_source_expansion" / "phase42.json"
            phase42_path.parent.mkdir(parents=True, exist_ok=True)
            phase42_path.write_text(json.dumps(phase42), encoding="utf-8")
            out_dir = root / "evaluation" / "four_source_expansion" / "phase44"

            report = module.build_report(trial_dir=trial_dir, phase42_json=phase42_path, out_dir=out_dir)

            self.assertEqual(report["processed_count"], 1)
            self.assertGreaterEqual(report["accepted_triples"], 5)
            predicates = {triple["predicate"] for triple in report["per_item_summary"][0]["accepted_triples_preview"]}
            self.assertIn("INSTANCE_OF", predicates)
            self.assertIn("SOURCE_URL", predicates)
            self.assertIn("HAS_TOPIC", predicates)
            self.assertIn("DISCOVERED_BY", predicates)
            self.assertEqual(len(list(out_dir.glob("*.json"))), 1)
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())

    def test_validation_rejects_low_confidence_missing_evidence_and_dedupes(self):
        module = load_module()
        triples = [
            module.make_triple("Apophis", "HAS_TOPIC", "asteroid", "Apophis asteroid", 0.9),
            module.make_triple("Apophis", "HAS_TOPIC", "asteroid", "Apophis asteroid", 0.9),
            module.make_triple("Apophis", "HAS_TOPIC", "space", "", 0.9),
            module.make_triple("Apophis", "HAS_TOPIC", "weak", "weak evidence", 0.4),
        ]

        accepted, warnings = module.validate_triples(triples, "https://science.nasa.gov/solar-system/asteroids/apophis/")

        self.assertEqual(len(accepted), 1)
        self.assertGreaterEqual(len(warnings), 3)
        self.assertEqual(accepted[0]["predicate"], "HAS_TOPIC")

    def test_output_paths_are_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "triples" / "phase44"
            exit_code = module.main(["--out-dir", str(bad)])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_network_or_formal_writes(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("urlopen", source)
        self.assertNotIn("fetch_url", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("data/triples", source.replace("\\", "/"))
        self.assertNotIn("neo4j_loader", source.lower())
        self.assertNotIn("chroma_store", source.lower())


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_nasa_limited_shadow_package.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_nasa_limited_shadow_package", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NasaLimitedShadowPackageTests(unittest.TestCase):
    def test_merges_mock_narratives_and_triples_package(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = root / "evaluation" / "four_source_expansion"
            narrative_dir = base / "phase43"
            relation_dir = base / "phase44"
            narrative_dir.mkdir(parents=True)
            relation_dir.mkdir(parents=True)
            narrative_item = {
                "source_id": "nasa",
                "title": "Apophis",
                "source_url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "narratives": [{"content": "Apophis is a near-Earth asteroid.", "section": "raw_chunk_1"}],
            }
            relation_item = {
                "source_id": "nasa",
                "title": "Apophis",
                "url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "triples_preview": [
                    {"subject": "Apophis", "predicate": "INSTANCE_OF", "object": "asteroid", "evidence": "Apophis is a near-Earth asteroid.", "confidence": 0.82},
                    {"subject": "Apophis", "predicate": "INSTANCE_OF", "object": "asteroid", "evidence": "duplicate", "confidence": 0.82},
                ],
            }
            (narrative_dir / "apophis.json").write_text(json.dumps(narrative_item), encoding="utf-8")
            (relation_dir / "apophis.json").write_text(json.dumps(relation_item), encoding="utf-8")
            out_dir = base / "package"
            approval = base / "approval.json"

            report = module.build_package(
                narrative_trial_json=base / "missing_phase43.json",
                narrative_trial_dir=narrative_dir,
                relation_preview_json=base / "missing_phase44.json",
                relation_preview_dir=relation_dir,
                out_dir=out_dir,
                approval_template=approval,
            )

            self.assertEqual(report["source_id"], "nasa")
            self.assertEqual(report["items"], 1)
            self.assertEqual(report["triples"], 1)
            self.assertEqual(report["narratives"], 1)
            self.assertEqual(report["approval_status"], "pending")
            self.assertTrue((out_dir / "package_manifest.json").exists())
            self.assertTrue((out_dir / "triples_preview.json").exists())
            self.assertTrue((out_dir / "narratives_preview.json").exists())
            self.assertTrue((out_dir / "review_sample.md").exists())
            self.assertEqual(json.loads(approval.read_text(encoding="utf-8"))["approval_decision"], "pending")
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())

    def test_only_nasa_and_invalid_triples_warned(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = root / "evaluation" / "four_source_expansion"
            narrative_dir = base / "phase43"
            relation_dir = base / "phase44"
            narrative_dir.mkdir(parents=True)
            relation_dir.mkdir(parents=True)
            (narrative_dir / "esa.json").write_text(json.dumps({"source_id": "esa", "title": "ESA", "narratives": [{"content": "skip"}]}), encoding="utf-8")
            (relation_dir / "bad.json").write_text(
                json.dumps({
                    "source_id": "nasa",
                    "title": "Weak",
                    "url": "https://science.nasa.gov/weak/",
                    "triples_preview": [
                        {"subject": "Weak", "predicate": "HAS_TOPIC", "object": "asteroid", "evidence": "", "confidence": 0.9},
                        {"subject": "Weak", "predicate": "HAS_TOPIC", "object": "asteroid", "evidence": "weak", "confidence": 0.3},
                    ],
                }),
                encoding="utf-8",
            )

            report = module.build_package(
                narrative_trial_json=base / "missing_phase43.json",
                narrative_trial_dir=narrative_dir,
                relation_preview_json=base / "missing_phase44.json",
                relation_preview_dir=relation_dir,
                out_dir=base / "package",
                approval_template=base / "approval.json",
            )

            self.assertEqual(report["items"], 1)
            self.assertEqual(report["triples"], 0)
            self.assertGreaterEqual(len(report["quality_flags"]), 2)

    def test_output_paths_are_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "triples" / "package"
            exit_code = module.main(["--out-dir", str(bad)])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_network_or_formal_writes(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("urlopen", source)
        self.assertNotIn("fetch_url", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("neo4j_loader", source.lower())
        self.assertNotIn("chroma_store", source.lower())


if __name__ == "__main__":
    unittest.main()

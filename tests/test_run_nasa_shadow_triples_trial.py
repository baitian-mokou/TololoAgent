import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_nasa_shadow_triples_trial.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_nasa_shadow_triples_trial", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NasaShadowTriplesTrialTests(unittest.TestCase):
    def test_selects_only_nasa_accepted_and_respects_limit(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_dir = root / "data" / "raw_json" / "nasa"
            raw_dir.mkdir(parents=True)
            raw_paths = []
            for index in range(2):
                path = raw_dir / f"nasa_{index}.json"
                path.write_text(
                    json.dumps({
                        "title": f"Asteroid {index}",
                        "source_url": f"https://science.nasa.gov/solar-system/asteroids/{index}/",
                        "html": "<html><body><p>NASA asteroid mission orbit science reference data.</p></body></html>",
                    }),
                    encoding="utf-8",
                )
                raw_paths.append(path)
            esa_path = root / "data" / "raw_json" / "esa" / "esa.json"
            esa_path.parent.mkdir(parents=True)
            esa_path.write_text(json.dumps({"title": "ESA", "text": "mission science"}), encoding="utf-8")
            preview = {
                "items": [
                    {"source_id": "nasa", "quality_triage": "accepted", "raw_path": str(raw_paths[0])},
                    {"source_id": "nasa", "quality_triage": "accepted", "raw_path": str(raw_paths[1])},
                    {"source_id": "nasa", "quality_triage": "review_needed", "raw_path": str(raw_paths[1])},
                    {"source_id": "esa", "quality_triage": "accepted", "raw_path": str(esa_path)},
                ]
            }
            preview_path = root / "evaluation" / "four_source_expansion" / "preview.json"
            preview_path.parent.mkdir(parents=True)
            preview_path.write_text(json.dumps(preview), encoding="utf-8")
            out_dir = root / "evaluation" / "four_source_expansion" / "trial"

            report = module.build_report(preview_json=preview_path, out_dir=out_dir, limit=1, root=root)

            self.assertEqual(report["source_id"], "nasa")
            self.assertEqual(report["input_raw_count"], 2)
            self.assertEqual(report["processed_count"], 1)
            self.assertEqual(len(list(out_dir.glob("*.json"))), 1)
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())

    def test_missing_raw_is_failed_not_crashing(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preview_path = root / "evaluation" / "four_source_expansion" / "preview.json"
            preview_path.parent.mkdir(parents=True)
            preview_path.write_text(
                json.dumps({"items": [{"source_id": "nasa", "quality_triage": "accepted", "raw_path": str(root / "missing.json")}]}),
                encoding="utf-8",
            )
            out_dir = root / "evaluation" / "four_source_expansion" / "trial"

            report = module.build_report(preview_json=preview_path, out_dir=out_dir, limit=20, root=root)

            self.assertEqual(report["processed_count"], 0)
            self.assertEqual(report["failed"], 1)
            self.assertIn("missing_raw", report["errors"][0]["error"])

    def test_cli_output_paths_are_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bad_dir = root / "data" / "triples" / "trial"
            exit_code = module.main(["--out-dir", str(bad_dir)])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad_dir.exists())

    def test_script_source_has_no_formal_or_destructive_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("materialize_source(", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("urlopen", source)
        self.assertNotIn("fetch_url", source)
        self.assertNotIn("TRIPLES_ROOT", source)
        self.assertNotIn("neo4j_loader", source.lower())
        self.assertNotIn("chroma_store", source.lower())


if __name__ == "__main__":
    unittest.main()

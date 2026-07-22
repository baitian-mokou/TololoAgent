import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preview_new_raw_materialization.py"


def load_module():
    spec = importlib.util.spec_from_file_location("preview_new_raw_materialization", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NewRawMaterializationPreviewTests(unittest.TestCase):
    def test_report_locates_written_raw_and_estimates_without_downstream_writes(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_path = root / "data" / "raw_json" / "nasa" / "asteroid.json"
            raw_path.parent.mkdir(parents=True)
            raw_path.write_text(
                json.dumps({
                    "title": "Asteroid Facts",
                    "source_url": "https://science.nasa.gov/solar-system/asteroids/facts/",
                    "html": "<html><head><title>Asteroid Facts</title></head><body>"
                    "<table><tr><td>Mass (10^20 kg)</td><td>1.0</td></tr></table>"
                    "<p>Asteroid planetary science mission orbit radius atmosphere reference data.</p>"
                    "</body></html>",
                }),
                encoding="utf-8",
            )
            ingest = {
                "sources": [{
                    "source_id": "nasa",
                    "items": [{"status": "written", "url": "https://science.nasa.gov/solar-system/asteroids/facts/", "saved_path": str(raw_path)}],
                }]
            }
            ingest_path = root / "evaluation" / "four_source_expansion" / "phase41.json"
            ingest_path.parent.mkdir(parents=True)
            ingest_path.write_text(json.dumps(ingest), encoding="utf-8")

            report = module.build_report(ingest_report=ingest_path, root=root)

            self.assertEqual(report["summary"]["new_raw_count"], 1)
            self.assertEqual(report["summary"]["readable_count"], 1)
            self.assertGreaterEqual(report["summary"]["preview_narratives_total"], 1)
            self.assertGreaterEqual(report["summary"]["preview_triples_total"], 1)
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())

    def test_missing_raw_warns_and_duplicate_groups_are_marked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_dir = root / "data" / "raw_json" / "esa"
            raw_dir.mkdir(parents=True)
            text = "Rosetta comet science mission orbit reference data " * 20
            paths = [raw_dir / "a.json", raw_dir / "b.json"]
            for path in paths:
                path.write_text(json.dumps({"title": "Rosetta", "source_url": "https://blogs.esa.int/rosetta/", "text": text}), encoding="utf-8")
            missing = raw_dir / "missing.json"
            ingest = {
                "sources": [{
                    "source_id": "esa",
                    "items": [
                        {"status": "written", "url": "https://blogs.esa.int/rosetta/", "saved_path": str(paths[0])},
                        {"status": "written", "url": "https://blogs.esa.int/rosetta/?utm=x", "saved_path": str(paths[1])},
                        {"status": "written", "url": "https://example.invalid/missing", "saved_path": str(missing)},
                    ],
                }]
            }
            ingest_path = root / "evaluation" / "four_source_expansion" / "phase41.json"
            ingest_path.parent.mkdir(parents=True)
            ingest_path.write_text(json.dumps(ingest), encoding="utf-8")

            report = module.build_report(ingest_report=ingest_path, root=root)

            self.assertEqual(report["summary"]["new_raw_count"], 3)
            self.assertEqual(report["summary"]["readable_count"], 2)
            self.assertEqual(report["summary"]["missing_raw_count"], 1)
            self.assertGreater(report["summary"]["duplicate_groups"], 0)
            duplicate_items = [item for item in report["items"] if item.get("duplicate_group")]
            self.assertEqual(len(duplicate_items), 2)

    def test_cli_writes_only_evaluation_or_docs_outputs(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "preview.json"
            exit_code = module.main(["--out-json", str(bad)])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_downstream_writes_or_network(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("urlopen", source)
        self.assertNotIn("fetch_url", source)
        self.assertNotIn("materialize_source(", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("TRIPLES_ROOT", source)
        self.assertNotIn("neo4j_loader", source.lower())
        self.assertNotIn("chroma_store", source.lower())


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_selected_raw_shadow_ingest.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_selected_raw_shadow_ingest", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SelectedRawShadowIngestTests(unittest.TestCase):
    def test_mock_fetch_writes_only_allowed_raw_dirs_and_honors_source_limits(self):
        module = load_module()

        selected = {
            "sources": [
                {
                    "source_id": "nasa",
                    "selected_candidates": [
                        {"url": "https://science.nasa.gov/solar-system/asteroids/facts/", "title": "Asteroids Facts"},
                        {"url": "https://science.nasa.gov/solar-system/asteroids/apophis/", "title": "Apophis"},
                    ],
                },
                {
                    "source_id": "esa",
                    "selected_candidates": [
                        {"url": "https://www.esa.int/Science_Exploration/Space_Science/Juice", "title": "Juice"},
                    ],
                },
            ]
        }

        def fake_fetch(url, timeout=15):
            return {
                "url": url,
                "content_type": "text/html",
                "body": "<html><head><title>Science Page</title></head><body>"
                "<p>Mission science planetary orbit atmosphere mass radius reference table data.</p>"
                "</body></html>",
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected_path = root / "evaluation" / "four_source_expansion" / "selected.json"
            selected_path.parent.mkdir(parents=True)
            selected_path.write_text(json.dumps(selected), encoding="utf-8")
            report = module.build_report(
                root=ROOT,
                selected_json=selected_path,
                source_limits={"nasa": 1, "esa": 1},
                raw_root=root / "data" / "raw_json",
                report_dir=root / "evaluation" / "four_source_expansion",
                fetcher=fake_fetch,
            )

            self.assertEqual(report["summary"]["new_records"], 2)
            self.assertEqual(report["summary"]["failed"], 0)
            self.assertEqual(len(list((root / "data" / "raw_json" / "nasa").glob("*.json"))), 1)
            self.assertEqual(len(list((root / "data" / "raw_json" / "esa").glob("*.json"))), 1)
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())

    def test_duplicate_url_is_skipped_without_overwriting(self):
        module = load_module()

        selected = {
            "sources": [{
                "source_id": "nasa",
                "selected_candidates": [{
                    "url": "https://science.nasa.gov/solar-system/asteroids/facts/?utm_source=x",
                    "title": "Asteroids Facts",
                }],
            }]
        }

        def fake_fetch(url, timeout=15):
            return {
                "url": url,
                "content_type": "text/html",
                "body": "<html><head><title>Asteroids Facts</title></head><body>science text reference mission</body></html>",
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_dir = root / "data" / "raw_json" / "nasa"
            raw_dir.mkdir(parents=True)
            existing = raw_dir / "existing.json"
            existing.write_text(
                json.dumps({"source_url": "https://science.nasa.gov/solar-system/asteroids/facts/", "title": "Asteroids Facts"}),
                encoding="utf-8",
            )
            selected_path = root / "evaluation" / "four_source_expansion" / "selected.json"
            selected_path.parent.mkdir(parents=True)
            selected_path.write_text(json.dumps(selected), encoding="utf-8")

            report = module.build_report(
                root=ROOT,
                selected_json=selected_path,
                source_limits={"nasa": 1},
                raw_root=root / "data" / "raw_json",
                report_dir=root / "evaluation" / "four_source_expansion",
                fetcher=fake_fetch,
            )

            item = report["sources"][0]
            self.assertEqual(item["new_records"], 0)
            self.assertEqual(item["duplicate_skipped"], 1)
            self.assertEqual(len(list(raw_dir.glob("*.json"))), 1)

    def test_only_nasa_esa_are_processed(self):
        module = load_module()

        selected = {
            "sources": [
                {"source_id": "wikidata", "selected_candidates": [{"url": "https://www.wikidata.org/wiki/Q2"}]},
                {"source_id": "zh_wikipedia", "selected_candidates": [{"url": "https://example.com"}]},
                {"source_id": "nasa", "selected_candidates": []},
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected_path = root / "evaluation" / "four_source_expansion" / "selected.json"
            selected_path.parent.mkdir(parents=True)
            selected_path.write_text(json.dumps(selected), encoding="utf-8")
            report = module.build_report(
                root=ROOT,
                selected_json=selected_path,
                source_limits={"nasa": 1, "wikidata": 1, "zh_wikipedia": 1},
                raw_root=root / "data" / "raw_json",
                report_dir=root / "evaluation" / "four_source_expansion",
                fetcher=lambda url, timeout=15: {},
            )

        self.assertEqual([item["source_id"] for item in report["sources"]], ["nasa"])
        self.assertEqual(report["skipped_sources"], ["wikidata", "zh_wikipedia"])

    def test_cli_output_paths_are_restricted(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "report.json"
            exit_code = module.main(["--out-json", str(bad)])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_downstream_or_destructive_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)
        self.assertNotIn("TRIPLES_DIR", source)
        self.assertNotIn("neo4j_loader", source)
        self.assertNotIn("chroma_store", source)


if __name__ == "__main__":
    unittest.main()

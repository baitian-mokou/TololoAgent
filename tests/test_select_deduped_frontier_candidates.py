import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "select_deduped_frontier_candidates.py"


def load_module():
    spec = importlib.util.spec_from_file_location("select_deduped_frontier_candidates", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DedupedFrontierCandidateTests(unittest.TestCase):
    def test_canonical_url_dedup_handles_query_and_trailing_slash(self):
        module = load_module()

        self.assertEqual(
            module.canonical_url("HTTPS://Science.NASA.GOV/solar-system/mars/?utm_source=x"),
            module.canonical_url("https://science.nasa.gov/solar-system/mars"),
        )

    def test_selects_unseen_candidates_and_blocks_failed_urls(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_dir = root / "data" / "raw_json" / "nasa"
            raw_dir.mkdir(parents=True)
            (raw_dir / "mars.json").write_text(
                json.dumps({
                    "title": "Mars",
                    "source_url": "https://science.nasa.gov/solar-system/mars/",
                    "url": "https://science.nasa.gov/solar-system/mars/?utm_campaign=x",
                }),
                encoding="utf-8",
            )
            frontier_dir = root / "evaluation" / "source_frontiers"
            frontier_dir.mkdir(parents=True)
            (frontier_dir / "nasa_frontier.json").write_text(
                json.dumps({
                    "accepted": [
                        {"url": "https://science.nasa.gov/solar-system/mars", "title": "Mars", "reason": "accepted"},
                        {"url": "https://science.nasa.gov/solar-system/dwarf-planets/", "title": "Dwarf Planets", "reason": "accepted"},
                        {"url": "https://science.nasa.gov/solar-system/jupiter/", "title": "Jupiter", "reason": "accepted", "quality_triage": "review_needed", "quality_score": 45},
                    ]
                }),
                encoding="utf-8",
            )
            phase39 = root / "evaluation" / "four_source_expansion"
            phase39.mkdir(parents=True)
            (phase39 / "nasa_raw_shadow_batch_trial_phase39_ingestion_report.json").write_text(
                json.dumps({"items": [{"url": "https://science.nasa.gov/solar-system/dwarf-planets/", "status": "failed"}]}),
                encoding="utf-8",
            )

            report = module.build_report(root=root, sources=["nasa"], limit=10)

        item = report["sources"][0]
        self.assertEqual(item["existing_raw_count"], 1)
        self.assertEqual(item["frontier_total"], 3)
        self.assertEqual(item["duplicate_candidates"], 1)
        self.assertEqual(item["failed_or_blocked_candidates"], 1)
        self.assertEqual(item["selected_count"], 1)
        self.assertEqual(item["selected_candidates"][0]["title"], "Jupiter")

    def test_title_fallback_dedup_when_url_missing(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_dir = root / "data" / "raw_json" / "esa"
            raw_dir.mkdir(parents=True)
            (raw_dir / "juice.json").write_text(json.dumps({"title": "ESA - Juice"}), encoding="utf-8")
            frontier_dir = root / "evaluation" / "source_frontiers"
            frontier_dir.mkdir(parents=True)
            (frontier_dir / "esa_frontier.json").write_text(
                json.dumps({"accepted": [{"title": "esa juice"}, {"title": "Rosetta"}]}),
                encoding="utf-8",
            )

            report = module.build_report(root=root, sources=["esa"], limit=10)

        item = report["sources"][0]
        self.assertEqual(item["duplicate_candidates"], 1)
        self.assertEqual(item["selected_candidates"][0]["title"], "Rosetta")

    def test_output_paths_are_limited_to_docs_or_four_source_evaluation(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "dedup.json"
            exit_code = module.main(["--sources", "nasa", "--out-json", str(bad)])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_network_ingest_or_data_writes(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("requests", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("ingest_frontier", source)
        self.assertNotIn("data/raw_json", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)


if __name__ == "__main__":
    unittest.main()

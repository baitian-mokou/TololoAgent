import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "report_offline_fixture_quality.py"


def load_module():
    spec = importlib.util.spec_from_file_location("report_offline_fixture_quality", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OfflineFixtureQualityReportTests(unittest.TestCase):
    def test_reports_approved_candidate_fixtures_without_network_or_formal_writes(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "offline.json"
            out_md = root / "evaluation" / "source_quality" / "sandbox" / "offline.md"

            exit_code = module.main([
                "--manifest-dir",
                str(ROOT / "configs" / "source_manifests" / "candidates"),
                "--source",
                "noaa_climate_candidate",
                "--source",
                "data_portal_candidate",
                "--fixture-dir",
                str(ROOT / "tests" / "fixtures" / "source_quality"),
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ])

            self.assertEqual(exit_code, 0)
            self.assertTrue(out_json.exists())
            self.assertTrue(out_md.exists())
            self.assertFalse((root / "data").exists())
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["execution_status"], "not_run")
            self.assertFalse(payload["network"])
            self.assertFalse(payload["formal_pipeline_write"])
            self.assertEqual(payload["summary"]["sources"], 2)
            self.assertGreaterEqual(payload["summary"]["total_samples"], 6)
            self.assertEqual({item["source_id"] for item in payload["items"]}, {"noaa_climate_candidate", "data_portal_candidate"})
            for source in payload["items"]:
                self.assertFalse(source["registered"])
                self.assertFalse(source["network"])
                self.assertEqual(source["execution_status"], "not_run")
                self.assertTrue(source["offline_fixture_only"])
                self.assertTrue(source["samples"])
                for sample in source["samples"]:
                    self.assertEqual(sample["source_sample_type"], "offline_fixture/manual_sample")
                    self.assertIn("triage", sample)
                    self.assertIn("reasons", sample)
                    self.assertIn("score", sample)
                    self.assertNotIn("html", sample)
                    self.assertNotIn("text", sample)
            self.assertIn("Offline Fixture Quality", out_md.read_text(encoding="utf-8"))

    def test_missing_fixture_reports_warning_without_creating_data_dir(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_dir = root / "manifests"
            manifest_dir.mkdir()
            (manifest_dir / "missing_fixture_candidate.json").write_text(json.dumps({
                "source_name": "missing_fixture_candidate",
                "source_mode": "official_science",
                "allowed_domains": ["missing.example.gov"],
                "seed_urls": ["https://missing.example.gov/science"],
                "include_path_keywords": ["science"],
                "exclude_path_keywords": ["search"],
                "topic_taxonomy": ["science"],
                "quality_gate": {
                    "accepted_min_score": 70,
                    "review_min_score": 35,
                    "allow_exploratory": True,
                    "skip_rejected_allowed": True,
                },
                "quality_notes": "test",
                "fixture_candidates": "tests/fixtures/source_quality/does_not_exist.json",
            }), encoding="utf-8")
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "missing.json"

            exit_code = module.main([
                "--manifest-dir",
                str(manifest_dir),
                "--source",
                "missing_fixture_candidate",
                "--fixture-dir",
                str(root / "fixtures"),
                "--out-json",
                str(out_json),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["items"][0]["sample_count"], 0)
            self.assertTrue(payload["items"][0]["warnings"])
            self.assertFalse((root / "data").exists())

    def test_output_paths_must_stay_under_evaluation_sandbox(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "offline.json"
            exit_code = module.main([
                "--manifest-dir",
                str(ROOT / "configs" / "source_manifests" / "candidates"),
                "--source",
                "noaa_climate_candidate",
                "--out-json",
                str(bad),
            ])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_network_ingest_or_delete_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("urllib", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("ingest", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)


if __name__ == "__main__":
    unittest.main()

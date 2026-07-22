import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_quality_gate_trial.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_quality_gate_trial", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QualityGateTrialTests(unittest.TestCase):
    def test_compare_reports_keeps_samples_compact(self):
        module = load_script()
        baseline = {
            "fetched_count": 2,
            "skipped_count": 0,
            "failed_count": 0,
            "quality_summary": {"triage_counts": {"accepted": 1, "rejected": 1}},
            "items": [
                {
                    "status": "fetched",
                    "title": "Mars Fact Sheet",
                    "url": "https://nasa.gov/mars",
                    "quality_triage": "accepted",
                    "quality_score": 95,
                    "quality_reasons": ["table evidence present"],
                    "quality_labels": ["fact_page"],
                    "text_length": 1000,
                    "content": "must not appear",
                },
                {
                    "status": "fetched",
                    "title": "Mars gallery",
                    "url": "https://nasa.gov/gallery/mars",
                    "quality_triage": "rejected",
                    "quality_score": 0,
                    "quality_reasons": ["media/gallery signal"],
                    "quality_labels": ["media_page"],
                    "text_length": 30,
                },
            ],
        }
        gated = {
            "fetched_count": 1,
            "skipped_count": 1,
            "failed_count": 0,
            "quality_summary": {"triage_counts": {"accepted": 1, "rejected": 1}},
            "items": [
                {
                    "status": "skipped",
                    "reason": "skipped_quality_rejected",
                    "title": "Mars gallery",
                    "url": "https://nasa.gov/gallery/mars",
                    "quality_triage": "rejected",
                    "quality_score": 0,
                    "quality_reasons": ["media/gallery signal"],
                    "quality_labels": ["media_page"],
                    "text_length": 30,
                }
            ],
        }

        summary = module.compare_source_reports("nasa", baseline, gated)

        self.assertEqual(summary["gated"]["skipped_quality_rejected"], 1)
        self.assertEqual(summary["false_kill_risk"], "low")
        self.assertEqual(len(summary["rejected_samples"]), 1)
        self.assertNotIn("content", summary["accepted_samples"][0])
        self.assertIn("review_needed_samples", summary)
        self.assertIn("exploratory_samples", summary)
        self.assertTrue(summary["recommend_skip_rejected_for_small_batch"])

    def test_wikidata_is_guarded_from_skip_rejected_trial(self):
        module = load_script()

        with self.assertRaises(ValueError):
            module.validate_sources(["wikidata"])

    def test_script_source_has_no_delete_operations(self):
        source = SCRIPT.read_text(encoding="utf-8")

        for token in ("Remove-Item", "shutil.rmtree", "os.remove", ".unlink(", ".rmdir("):
            self.assertNotIn(token, source)

    def test_write_report_creates_json_without_formal_data_paths(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "quality_gate_phase13_report.json"
            module.write_json(path, {"sources": {}})
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload, {"sources": {}})


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preview_approved_small_batch_plan.py"
REVIEW_SCRIPT = ROOT / "scripts" / "report_sandbox_candidate_reviews.py"


def load_module():
    spec = importlib.util.spec_from_file_location("preview_approved_small_batch_plan", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_review_module():
    spec = importlib.util.spec_from_file_location("report_sandbox_candidate_reviews", REVIEW_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApprovedSmallBatchPlanPreviewTests(unittest.TestCase):
    def make_summary(self, root: Path, decisions: dict | None = None) -> Path:
        review = load_review_module()
        summary = review.build_summary(
            ROOT / "configs" / "source_manifests" / "examples",
            root / "evaluation" / "source_quality" / "sandbox",
        )
        if decisions:
            review.apply_review_decisions(summary, decisions)
        path = root / "evaluation" / "source_quality" / "sandbox" / "summary.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
        return path

    def test_approved_source_generates_not_run_plan_item(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary_path = self.make_summary(root, {
                "official_science_example": {
                    "source_id": "official_science_example",
                    "review_decision": "approved_for_small_batch",
                    "approved_sample_size": 12,
                    "reviewer_notes": "ok",
                }
            })
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "plan.json"
            out_md = root / "evaluation" / "source_quality" / "sandbox" / "plan.md"

            exit_code = module.main([
                "--review-summary-json",
                str(summary_path),
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["plan_items"], 1)
            item = payload["items"][0]
            self.assertEqual(item["source_id"], "official_science_example")
            self.assertEqual(item["approved_sample_size"], 12)
            self.assertEqual(item["execution_status"], "not_run")
            self.assertTrue(item["quality_guard_required"])
            self.assertTrue(item["network_required_for_future_run"])
            self.assertFalse((root / "data").exists())
            self.assertIn("计划预览，不是执行结果", out_md.read_text(encoding="utf-8"))

    def test_candidate_review_decisions_generate_two_candidate_plan_items(self):
        module = load_module()
        review = load_review_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sandbox_dir = root / "evaluation" / "source_quality" / "sandbox"
            summary = review.build_summary(ROOT / "configs" / "source_manifests" / "candidates", sandbox_dir)
            decisions = review.load_review_decisions(ROOT / "tests" / "fixtures" / "source_quality" / "candidate_review_decisions_phase29.json")
            review.apply_review_decisions(summary, decisions)
            summary_path = sandbox_dir / "candidate_summary_filled.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
            out_json = sandbox_dir / "candidate_plan.json"

            exit_code = module.main([
                "--review-summary-json",
                str(summary_path),
                "--out-json",
                str(out_json),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["plan_items"], 2)
            self.assertEqual(payload["execution_status"], "not_run")
            self.assertFalse(payload["network"])
            self.assertFalse(payload["formal_pipeline_write"])
            source_ids = {item["source_id"] for item in payload["items"]}
            self.assertEqual(source_ids, {"noaa_climate_candidate", "data_portal_candidate"})
            self.assertTrue(all(item["execution_status"] == "not_run" for item in payload["items"]))
            self.assertTrue(all(item["quality_guard_required"] for item in payload["items"]))
            self.assertFalse((root / "data").exists())

    def test_non_approved_sources_are_excluded_and_empty_plan_is_ok(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary_path = self.make_summary(root)
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "empty_plan.json"
            exit_code = module.main([
                "--review-summary-json",
                str(summary_path),
                "--out-json",
                str(out_json),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["plan_items"], 0)
            self.assertEqual(payload["items"], [])

    def test_approved_sample_size_must_be_positive(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary_path = self.make_summary(root, {
                "official_science_example": {
                    "source_id": "official_science_example",
                    "review_decision": "approved_for_small_batch",
                    "approved_sample_size": 0,
                }
            })
            exit_code = module.main([
                "--review-summary-json",
                str(summary_path),
                "--out-json",
                str(root / "evaluation" / "source_quality" / "sandbox" / "bad.json"),
            ])

            self.assertEqual(exit_code, 2)

    def test_output_paths_must_stay_under_sandbox(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary_path = self.make_summary(root)
            bad = root / "data" / "plan.json"
            exit_code = module.main([
                "--review-summary-json",
                str(summary_path),
                "--out-json",
                str(bad),
            ])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_network_ingest_or_delete_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("urllib", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("ingest_frontier", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "report_sandbox_candidate_reviews.py"


def load_module():
    spec = importlib.util.spec_from_file_location("report_sandbox_candidate_reviews", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SandboxCandidateReviewReportTests(unittest.TestCase):
    def test_reports_examples_to_json_and_markdown_with_recommendations(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "summary.json"
            out_md = root / "evaluation" / "source_quality" / "sandbox" / "summary.md"

            exit_code = module.main([
                "--manifest-dir",
                str(ROOT / "configs" / "source_manifests" / "examples"),
                "--sandbox-dir",
                str(root / "evaluation" / "source_quality" / "sandbox"),
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
            self.assertGreaterEqual(payload["summary"]["sources"], 4)
            self.assertIn("recommendation_counts", payload["summary"])
            self.assertTrue(all("recommendation" in item for item in payload["items"]))
            self.assertTrue(all(item["network"] is False for item in payload["items"]))
            self.assertGreaterEqual(sum(item["candidate_count"] for item in payload["items"]), 12)
            all_triages = {
                triage
                for item in payload["items"]
                for triage, count in {
                    "accepted": item["accepted"],
                    "review_needed": item["review_needed"],
                    "exploratory": item["exploratory"],
                    "rejected": item["rejected"],
                }.items()
                if count
            }
            self.assertGreaterEqual(len(all_triages), 3)
            self.assertTrue(any(item["rejected"] for item in payload["items"]))
            self.assertGreaterEqual(len(payload["summary"]["recommendation_counts"]), 2)
            for item in payload["items"]:
                self.assertIn("review_decision", item)
                self.assertIn("review_required", item)
                self.assertIn("sample_size_recommended", item)
                self.assertIn("next_action", item)
                self.assertIn("reviewer_notes_template", item)
            markdown = out_md.read_text(encoding="utf-8")
            self.assertIn("Sandbox Candidate Review", markdown)
            self.assertIn("Manual Review Decisions", markdown)
            self.assertIn("Candidate Samples", markdown)

    def test_reports_candidate_manifests_as_unregistered_offline_sources(self):
        module = load_module()
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "candidates.json"
            out_md = root / "evaluation" / "source_quality" / "sandbox" / "candidates.md"

            exit_code = module.main([
                "--manifest-dir",
                str(ROOT / "configs" / "source_manifests" / "candidates"),
                "--sandbox-dir",
                str(root / "evaluation" / "source_quality" / "sandbox"),
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertGreaterEqual(payload["summary"]["sources"], 4)
            self.assertGreaterEqual(len(payload["summary"]["recommendation_counts"]), 2)
            self.assertTrue(all(item["registered"] is False for item in payload["items"]))
            self.assertTrue(all(item["network"] is False for item in payload["items"]))
            self.assertEqual(config.ACTIVE_SOURCE, "zh_wikipedia")
            self.assertFalse(any(item["source_id"] in config.SOURCE_REGISTRY for item in payload["items"]))

    def test_recommendation_rules_are_conservative(self):
        module = load_module()

        self.assertEqual(module.recommend({"candidate_count": 0, "triage_counts": {}}), "needs_manifest_fix")
        self.assertEqual(module.recommend({"candidate_count": 3, "triage_counts": {"rejected": 2}}), "needs_manifest_fix")
        self.assertEqual(module.recommend({"candidate_count": 2, "triage_counts": {"review_needed": 2}}), "manual_sample_first")
        self.assertEqual(module.recommend({"candidate_count": 2, "triage_counts": {"accepted": 1, "review_needed": 1}}), "ready_for_small_batch")
        self.assertEqual(module.recommend({"candidate_count": 4, "accepted": 2, "rejected": 1}), "ready_for_small_batch")
        self.assertEqual(module.recommend({"candidate_count": 4, "accepted": 0, "rejected": 3}), "needs_manifest_fix")
        self.assertEqual(
            module.recommend({"candidate_count": 2, "source_mode": "entity_data", "triage_counts": {"accepted": 2}}),
            "source_specific_gate",
        )

    def test_review_decision_defaults_are_manual_and_conservative(self):
        module = load_module()

        ready = module.review_decision({"recommendation": "ready_for_small_batch"})
        self.assertEqual(ready["review_decision"], "pending")
        self.assertTrue(ready["review_required"])
        self.assertEqual(ready["sample_size_recommended"], "10-20")
        self.assertIn("manual approve", ready["next_action"])

        needs_fix = module.review_decision({"recommendation": "needs_manifest_fix"})
        self.assertEqual(needs_fix["review_decision"], "needs_manifest_fix")
        self.assertEqual(needs_fix["sample_size_recommended"], 0)

        source_specific = module.review_decision({"recommendation": "source_specific_gate"})
        self.assertEqual(source_specific["review_decision"], "pending")
        self.assertIn("source-specific", source_specific["next_action"])

    def test_writes_review_template(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "evaluation" / "source_quality" / "sandbox" / "decisions_template.json"
            exit_code = module.main([
                "--manifest-dir",
                str(ROOT / "configs" / "source_manifests" / "examples"),
                "--sandbox-dir",
                str(root / "evaluation" / "source_quality" / "sandbox"),
                "--out-json",
                str(root / "evaluation" / "source_quality" / "sandbox" / "summary.json"),
                "--write-review-template",
                str(template),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(template.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertTrue(payload["sources"])
            self.assertIn("review_decision", payload["sources"][0])
            self.assertIn("reviewer_notes", payload["sources"][0])
            self.assertIn("approved_sample_size", payload["sources"][0])

    def test_review_decisions_file_overrides_report_only(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            decisions = root / "evaluation" / "source_quality" / "sandbox" / "decisions.json"
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "summary.json"
            decisions.parent.mkdir(parents=True, exist_ok=True)
            decisions.write_text(json.dumps({
                "schema_version": 1,
                "sources": [{
                    "source_id": "official_science_example",
                    "review_decision": "approved_for_small_batch",
                    "reviewer_notes": "抽样通过。",
                    "approved_sample_size": 12,
                }],
            }, ensure_ascii=False), encoding="utf-8")

            exit_code = module.main([
                "--manifest-dir",
                str(ROOT / "configs" / "source_manifests" / "examples"),
                "--sandbox-dir",
                str(root / "evaluation" / "source_quality" / "sandbox"),
                "--out-json",
                str(out_json),
                "--review-decisions",
                str(decisions),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            official = next(item for item in payload["items"] if item["source_id"] == "official_science_example")
            self.assertEqual(official["review_decision"], "approved_for_small_batch")
            self.assertEqual(official["reviewer_notes"], "抽样通过。")
            self.assertEqual(official["approved_sample_size"], 12)
            self.assertIn("plan small-batch ingest", official["next_action"])
            self.assertFalse((root / "data").exists())

    def test_invalid_review_decision_exits_nonzero(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            decisions = root / "evaluation" / "source_quality" / "sandbox" / "bad_decisions.json"
            decisions.parent.mkdir(parents=True, exist_ok=True)
            decisions.write_text(json.dumps({
                "schema_version": 1,
                "sources": [{"source_id": "academic_example", "review_decision": "ship_it"}],
            }), encoding="utf-8")

            exit_code = module.main([
                "--manifest-dir",
                str(ROOT / "configs" / "source_manifests" / "examples"),
                "--sandbox-dir",
                str(root / "evaluation" / "source_quality" / "sandbox"),
                "--review-decisions",
                str(decisions),
            ])

            self.assertEqual(exit_code, 2)

    def test_unknown_review_decision_source_exits_nonzero(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            decisions = root / "evaluation" / "source_quality" / "sandbox" / "unknown_decisions.json"
            decisions.parent.mkdir(parents=True, exist_ok=True)
            decisions.write_text(json.dumps({
                "schema_version": 1,
                "sources": [{"source_id": "unknown_source", "review_decision": "pending"}],
            }), encoding="utf-8")

            exit_code = module.main([
                "--manifest-dir",
                str(ROOT / "configs" / "source_manifests" / "examples"),
                "--sandbox-dir",
                str(root / "evaluation" / "source_quality" / "sandbox"),
                "--review-decisions",
                str(decisions),
            ])

            self.assertEqual(exit_code, 2)

    def test_output_paths_must_stay_under_evaluation_sandbox(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            bad_json = Path(temp_dir) / "data" / "summary.json"
            exit_code = module.main([
                "--manifest-dir",
                str(ROOT / "configs" / "source_manifests" / "examples"),
                "--out-json",
                str(bad_json),
            ])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad_json.exists())

    def test_script_source_has_no_network_or_delete_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("urllib", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("Remove-Item", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_preview_network_probe_plan.py"


def load_module():
    spec = importlib.util.spec_from_file_location("render_preview_network_probe_plan", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreviewNetworkProbePlanTests(unittest.TestCase):
    def test_renders_two_not_executed_preview_items_from_approved_plan(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "probe.json"
            out_md = root / "evaluation" / "source_quality" / "sandbox" / "probe.md"

            exit_code = module.main([
                "--approved-plan-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "candidate_science_sites_approved_plan_phase29.json"),
                "--offline-quality-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "offline_fixture_quality_phase30.json"),
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["execution_status"], "not_run")
            self.assertFalse(payload["network"])
            self.assertFalse(payload["formal_pipeline_write"])
            self.assertEqual(payload["summary"]["plan_items"], 2)
            source_ids = {item["source_id"] for item in payload["items"]}
            self.assertEqual(source_ids, {"noaa_climate_candidate", "data_portal_candidate"})
            for item in payload["items"]:
                self.assertLessEqual(item["max_pages"], 10)
                self.assertTrue(item["preview_only"])
                self.assertTrue(item["quality_gate_required"])
                self.assertTrue(item["requires_explicit_user_approval"])
                self.assertEqual(item["execution_status"], "not_run")
                self.assertFalse(item["network"])
                self.assertIn("NOT EXECUTED", item["proposed_command"])
                self.assertIn("preview_source_frontier.py", item["proposed_command"])
                self.assertTrue(item["allowed_domains"] or item["seed_urls"])
            self.assertFalse((root / "data").exists())
            self.assertIn("NOT EXECUTED", out_md.read_text(encoding="utf-8"))

    def test_offline_quality_all_rejected_blocks_source(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            approved_plan = root / "evaluation" / "source_quality" / "sandbox" / "approved.json"
            offline_quality = root / "evaluation" / "source_quality" / "sandbox" / "offline.json"
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "probe.json"
            approved_plan.parent.mkdir(parents=True, exist_ok=True)
            approved_plan.write_text(json.dumps({
                "items": [{
                    "source_id": "noaa_climate_candidate",
                    "approved_sample_size": 8,
                    "execution_status": "not_run",
                }]
            }), encoding="utf-8")
            offline_quality.write_text(json.dumps({
                "items": [{
                    "source_id": "noaa_climate_candidate",
                    "sample_count": 2,
                    "triage_counts": {"rejected": 2},
                }]
            }), encoding="utf-8")

            exit_code = module.main([
                "--approved-plan-json",
                str(approved_plan),
                "--offline-quality-json",
                str(offline_quality),
                "--out-json",
                str(out_json),
            ])

            self.assertEqual(exit_code, 0)
            item = json.loads(out_json.read_text(encoding="utf-8"))["items"][0]
            self.assertEqual(item["probe_status"], "blocked")
            self.assertIn("needs_quality_review", item["block_reasons"])

    def test_non_approved_sources_are_not_added(self):
        module = load_module()

        plan = {
            "items": [
                {"source_id": "approved", "approved_sample_size": 5},
                {"source_id": "pending", "approved_sample_size": 0},
            ]
        }
        report = module.build_plan(plan, {}, ROOT / "configs" / "source_manifests" / "candidates")
        self.assertEqual([item["source_id"] for item in report["items"]], ["approved"])

    def test_output_paths_must_stay_under_sandbox(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "probe.json"
            exit_code = module.main([
                "--approved-plan-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "candidate_science_sites_approved_plan_phase29.json"),
                "--out-json",
                str(bad),
            ])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_network_delete_or_formal_write_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("urllib", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)


if __name__ == "__main__":
    unittest.main()

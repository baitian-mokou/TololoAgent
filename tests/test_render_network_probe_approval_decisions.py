import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_network_probe_approval_decisions.py"


def load_module():
    spec = importlib.util.spec_from_file_location("render_network_probe_approval_decisions", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NetworkProbeApprovalDecisionsTests(unittest.TestCase):
    def test_writes_template_for_two_sources(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "evaluation" / "source_quality" / "sandbox" / "template.json"
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "report.json"

            exit_code = module.main([
                "--approval-package-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "network_probe_approval_package_phase32.json"),
                "--write-template",
                str(template),
                "--out-json",
                str(out_json),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(template.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(len(payload["items"]), 2)
            self.assertTrue(all(item["approval_decision"] == "pending" for item in payload["items"]))
            self.assertTrue(all("approved_max_pages" in item for item in payload["items"]))
            self.assertFalse((root / "data").exists())

    def test_applies_valid_decisions_without_execution(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            decisions = root / "evaluation" / "source_quality" / "sandbox" / "decisions.json"
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "filled.json"
            out_md = root / "evaluation" / "source_quality" / "sandbox" / "filled.md"
            decisions.parent.mkdir(parents=True, exist_ok=True)
            decisions.write_text(json.dumps({
                "schema_version": 1,
                "items": [
                    {
                        "source_id": "noaa_climate_candidate",
                        "approval_decision": "approved_for_preview_probe",
                        "reviewer_notes": "Approve a tiny preview only.",
                        "approved_max_pages": 5,
                    },
                    {
                        "source_id": "data_portal_candidate",
                        "approval_decision": "rejected",
                        "reviewer_notes": "Hold this source.",
                        "approved_max_pages": 0,
                    },
                ],
            }), encoding="utf-8")

            exit_code = module.main([
                "--approval-package-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "network_probe_approval_package_phase32.json"),
                "--approval-decisions",
                str(decisions),
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
            self.assertEqual(payload["summary"]["decision_counts"], {
                "approved_for_preview_probe": 1,
                "rejected": 1,
            })
            by_source = {item["source_id"]: item for item in payload["items"]}
            self.assertEqual(by_source["noaa_climate_candidate"]["approval_status"], "approved_for_manual_preview")
            self.assertEqual(by_source["noaa_climate_candidate"]["approved_max_pages"], 5)
            self.assertEqual(by_source["noaa_climate_candidate"]["execution_status"], "not_run")
            self.assertFalse(by_source["noaa_climate_candidate"]["network"])
            self.assertEqual(by_source["data_portal_candidate"]["approval_status"], "rejected")
            self.assertIn("APPROVED DOES NOT EXECUTE NETWORK", out_md.read_text(encoding="utf-8"))

    def test_approved_max_pages_cannot_exceed_package_limit(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            decisions = root / "evaluation" / "source_quality" / "sandbox" / "bad.json"
            decisions.parent.mkdir(parents=True, exist_ok=True)
            decisions.write_text(json.dumps({
                "items": [{
                    "source_id": "noaa_climate_candidate",
                    "approval_decision": "approved_for_preview_probe",
                    "approved_max_pages": 99,
                }]
            }), encoding="utf-8")

            exit_code = module.main([
                "--approval-package-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "network_probe_approval_package_phase32.json"),
                "--approval-decisions",
                str(decisions),
            ])

            self.assertEqual(exit_code, 2)

    def test_unknown_source_and_invalid_decision_fail(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            decisions = root / "evaluation" / "source_quality" / "sandbox" / "bad.json"
            decisions.parent.mkdir(parents=True, exist_ok=True)
            decisions.write_text(json.dumps({
                "items": [
                    {"source_id": "unknown", "approval_decision": "pending", "approved_max_pages": 0},
                    {"source_id": "noaa_climate_candidate", "approval_decision": "ship_it", "approved_max_pages": 0},
                ]
            }), encoding="utf-8")

            exit_code = module.main([
                "--approval-package-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "network_probe_approval_package_phase32.json"),
                "--approval-decisions",
                str(decisions),
            ])

            self.assertEqual(exit_code, 2)

    def test_output_paths_must_stay_under_sandbox(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "report.json"
            exit_code = module.main([
                "--approval-package-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "network_probe_approval_package_phase32.json"),
                "--out-json",
                str(bad),
            ])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_network_or_execution_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("urllib", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("preview_source_frontier.py --fetch-links", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)


if __name__ == "__main__":
    unittest.main()

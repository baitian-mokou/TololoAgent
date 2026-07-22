import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_manual_preview_command_card.py"


def load_module():
    spec = importlib.util.spec_from_file_location("render_manual_preview_command_card", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ManualPreviewCommandCardTests(unittest.TestCase):
    def test_approved_noaa_generates_single_not_run_command_card(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "card.json"
            out_md = root / "evaluation" / "source_quality" / "sandbox" / "card.md"

            exit_code = module.main([
                "--approval-decisions-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "network_probe_approval_decisions_phase33_filled.json"),
                "--source",
                "noaa_climate_candidate",
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
            self.assertEqual(payload["summary"]["command_cards"], 1)
            card = payload["items"][0]
            self.assertEqual(card["source_id"], "noaa_climate_candidate")
            self.assertEqual(card["approved_max_pages"], 5)
            self.assertEqual(card["execution_status"], "not_run")
            self.assertFalse(card["network"])
            self.assertFalse(card["formal_pipeline_write"])
            self.assertIn("NOT EXECUTED", card["manual_command"])
            self.assertIn("MANUAL ONLY", card["manual_command"])
            self.assertIn("PREVIEW ONLY", card["manual_command"])
            self.assertTrue(all(path.startswith("evaluation/source_quality/sandbox/") for path in card["expected_outputs"]))
            checklist = " ".join(card["preflight_checklist"]).lower()
            self.assertIn("active_source", checklist)
            self.assertIn("quality gate", checklist)
            self.assertIn("no formal write", checklist)
            self.assertFalse((root / "data").exists())
            self.assertIn("Manual Preview Command Card", out_md.read_text(encoding="utf-8"))

    def test_pending_source_request_fails_stably(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "pending.json"
            exit_code = module.main([
                "--approval-decisions-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "network_probe_approval_decisions_phase33_filled.json"),
                "--source",
                "data_portal_candidate",
                "--out-json",
                str(out_json),
            ])

            self.assertEqual(exit_code, 2)
            self.assertFalse(out_json.exists())

    def test_without_source_outputs_all_approved_sources_only(self):
        module = load_module()

        report = module.build_cards(
            json.loads((ROOT / "evaluation" / "source_quality" / "sandbox" / "network_probe_approval_decisions_phase33_filled.json").read_text(encoding="utf-8")),
            [],
        )
        self.assertEqual([item["source_id"] for item in report["items"]], ["noaa_climate_candidate"])

    def test_output_paths_must_stay_under_sandbox(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "card.json"
            exit_code = module.main([
                "--approval-decisions-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "network_probe_approval_decisions_phase33_filled.json"),
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

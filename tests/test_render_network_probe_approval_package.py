import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_network_probe_approval_package.py"


def load_module():
    spec = importlib.util.spec_from_file_location("render_network_probe_approval_package", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NetworkProbeApprovalPackageTests(unittest.TestCase):
    def test_renders_two_pending_approval_items(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "approval.json"
            out_md = root / "evaluation" / "source_quality" / "sandbox" / "approval.md"

            exit_code = module.main([
                "--probe-plan-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "preview_network_probe_plan_phase31.json"),
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["approval_status"], "pending_user_approval")
            self.assertEqual(payload["execution_status"], "not_run")
            self.assertFalse(payload["network"])
            self.assertFalse(payload["formal_pipeline_write"])
            self.assertEqual(payload["summary"]["approval_items"], 2)
            for item in payload["items"]:
                self.assertEqual(item["execution_status"], "not_run")
                self.assertFalse(item["network"])
                self.assertIn("NOT EXECUTED", item["preview_command"])
                checklist = " ".join(item["checklist"]).lower()
                self.assertIn("domain", checklist)
                self.assertIn("rate limit", checklist)
                self.assertIn("no formal write", checklist)
                self.assertTrue(item["risks"])
                self.assertTrue(item["expected_report_paths"])
            self.assertFalse((root / "data").exists())
            markdown = out_md.read_text(encoding="utf-8")
            self.assertIn("pending_user_approval", markdown)
            self.assertIn("confirm_domains", markdown)

    def test_empty_plan_renders_empty_package(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = root / "evaluation" / "source_quality" / "sandbox" / "empty_plan.json"
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "empty_approval.json"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(json.dumps({"items": []}), encoding="utf-8")

            exit_code = module.main([
                "--probe-plan-json",
                str(plan),
                "--out-json",
                str(out_json),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["approval_items"], 0)
            self.assertEqual(payload["items"], [])

    def test_output_paths_must_stay_under_sandbox(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "approval.json"
            exit_code = module.main([
                "--probe-plan-json",
                str(ROOT / "evaluation" / "source_quality" / "sandbox" / "preview_network_probe_plan_phase31.json"),
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

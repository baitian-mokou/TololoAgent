import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "report_project_stage_index.py"


def load_module():
    spec = importlib.util.spec_from_file_location("report_project_stage_index", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProjectStageIndexTests(unittest.TestCase):
    def test_generates_json_and_markdown_index(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_json = root / "evaluation" / "project_stage_index.json"
            out_md = root / "docs" / "project_stage_index.md"

            exit_code = module.main([
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["current_stage"], "Phase 36 index")
            self.assertEqual(payload["previous_stage"], "Phase 35 complete")
            self.assertEqual(payload["source_status"]["active_source"], "zh_wikipedia")
            self.assertFalse(payload["source_status"]["candidate_registered"])
            self.assertIn("report_index", payload)
            self.assertIn("verification_commands", payload)
            self.assertIn("safety_boundaries", payload)
            self.assertIn("next_routes", payload)
            self.assertIn("项目状态索引", out_md.read_text(encoding="utf-8"))

    def test_missing_reports_are_marked_missing(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            report = module.build_index(Path(temp_dir))
            statuses = {item["path"]: item["status"] for item in report["report_index"]}

        self.assertEqual(statuses["docs/source_expansion_delivery_report.md"], "missing")
        self.assertEqual(statuses["evaluation/source_quality/sandbox/manual_preview_command_card_phase34.json"], "missing")

    def test_output_paths_are_limited_to_docs_or_evaluation(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "project_stage_index.json"
            exit_code = module.main(["--out-json", str(bad)])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_does_not_touch_formal_data_pipeline(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("data/raw_json", source)
        self.assertNotIn("data/triples", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("urllib", source)


if __name__ == "__main__":
    unittest.main()

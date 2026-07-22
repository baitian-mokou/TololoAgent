import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan_four_source_batch_expansion.py"


def load_module():
    spec = importlib.util.spec_from_file_location("plan_four_source_batch_expansion", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FourSourceBatchExpansionPlanTests(unittest.TestCase):
    def test_generates_four_source_json_and_markdown(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_json = root / "evaluation" / "four_source_expansion" / "plan.json"
            out_md = root / "docs" / "four_source_batch_expansion_plan.md"

            exit_code = module.main([
                "--batch-size",
                "50",
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["phase"], "Phase 37")
            self.assertEqual(payload["active_source"], "zh_wikipedia")
            self.assertEqual(payload["summary"]["targets"], 4)
            self.assertEqual([item["source_id"] for item in payload["sources"]], ["zh_wikipedia", "nasa", "esa", "wikidata"])
            by_source = {item["source_id"]: item for item in payload["sources"]}
            self.assertEqual(by_source["zh_wikipedia"]["materialization_scope"], "formal_candidate")
            for source in ("nasa", "esa", "wikidata"):
                self.assertEqual(by_source[source]["mode"], "disabled")
                self.assertEqual(by_source[source]["materialization_scope"], "shadow_only")
                self.assertTrue(by_source[source]["quality_gate_required"])
            self.assertIn("四源扩批计划", out_md.read_text(encoding="utf-8"))

    def test_batch_size_can_be_changed_to_100(self):
        module = load_module()

        report = module.build_plan(batch_size=100)

        self.assertTrue(all(item["proposed_batch_size"] == 100 for item in report["sources"]))
        self.assertTrue(all(item["proposed_next_target_count"] >= item["current_raw_count"] for item in report["sources"]))

    def test_missing_report_or_data_is_warning_not_crash(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            report = module.build_plan(root=Path(temp_dir), batch_size=50)

        self.assertEqual(len(report["sources"]), 4)
        self.assertTrue(any(item["warnings"] for item in report["sources"]))
        self.assertTrue(any("missing" in warning for item in report["sources"] for warning in item["warnings"]))

    def test_output_paths_are_limited_to_docs_or_evaluation(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "data" / "plan.json"
            exit_code = module.main(["--out-json", str(bad)])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_network_ingest_or_delete_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("requests", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("crawl", source.lower())
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_four_source_batch_preview.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_four_source_batch_preview", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FourSourceBatchPreviewTests(unittest.TestCase):
    def test_offline_preview_generates_four_source_summary_and_safety_flags(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_json = root / "evaluation" / "four_source_expansion" / "preview.json"
            out_md = root / "docs" / "preview.md"

            exit_code = module.main([
                "--plan-json",
                str(ROOT / "evaluation" / "four_source_expansion" / "four_source_batch_plan_phase37.json"),
                "--batch-size",
                "50",
                "--offline-only",
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["phase"], "Phase 38")
            self.assertEqual(payload["active_source"], "zh_wikipedia")
            self.assertTrue(payload["offline_only"])
            self.assertEqual([item["source_id"] for item in payload["sources"]], ["zh_wikipedia", "nasa", "esa", "wikidata"])
            by_source = {item["source_id"]: item for item in payload["sources"]}
            self.assertEqual(by_source["zh_wikipedia"]["recommended_next_action"], "keep_baseline")
            self.assertEqual(by_source["zh_wikipedia"]["preview_execution"], "skipped_with_reason")
            for source in ("nasa", "esa", "wikidata"):
                self.assertEqual(by_source[source]["preview_execution"], "offline_reused")
                self.assertIn(by_source[source]["recommended_next_action"], {"raw_shadow_ingest_candidate", "needs_manual_review"})
                self.assertFalse(by_source[source]["safety_flags"]["formal_pipeline_write"])
                self.assertFalse(by_source[source]["safety_flags"]["chroma_write"])
                self.assertFalse(by_source[source]["safety_flags"]["neo4j_write"])
                self.assertTrue(by_source[source]["safety_flags"]["active_source_unchanged"])
            self.assertIn("四源 batch preview", out_md.read_text(encoding="utf-8"))

    def test_missing_quality_report_is_skipped_not_crash(self):
        module = load_module()
        plan = {
            "active_source": "zh_wikipedia",
            "sources": [
                {"source_id": "nasa", "mode": "disabled", "materialization_scope": "shadow_only"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan_path = root / "evaluation" / "four_source_expansion" / "plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            report = module.build_preview(plan_path=plan_path, root=root, batch_size=50, offline_only=True)

        item = report["sources"][0]
        self.assertEqual(item["preview_execution"], "skipped_with_reason")
        self.assertEqual(item["candidate_count"], 0)
        self.assertIn("missing", item["quality_gate_summary"]["reason"])

    def test_zh_wikipedia_is_never_shadow_ingest_candidate(self):
        module = load_module()

        report = module.build_preview(
            plan_path=ROOT / "evaluation" / "four_source_expansion" / "four_source_batch_plan_phase37.json",
            batch_size=50,
            offline_only=True,
        )
        zh = next(item for item in report["sources"] if item["source_id"] == "zh_wikipedia")

        self.assertNotEqual(zh["recommended_next_action"], "raw_shadow_ingest_candidate")
        self.assertEqual(zh["recommended_next_action"], "keep_baseline")

    def test_output_paths_are_limited_to_docs_or_four_source_evaluation(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "evaluation" / "source_quality" / "preview.json"
            exit_code = module.main([
                "--plan-json",
                str(ROOT / "evaluation" / "four_source_expansion" / "four_source_batch_plan_phase37.json"),
                "--out-json",
                str(bad),
            ])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_network_or_formal_pipeline_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("requests", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("crawl", source.lower())
        self.assertNotIn("ingest_manifest", source.lower())
        self.assertNotIn("data/raw_json", source)
        self.assertNotIn("data/triples", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)


if __name__ == "__main__":
    unittest.main()

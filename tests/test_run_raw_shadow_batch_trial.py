import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_raw_shadow_batch_trial.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_raw_shadow_batch_trial", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RawShadowBatchTrialTests(unittest.TestCase):
    def test_dry_run_reports_nasa_esa_without_raw_or_downstream_writes(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_json = root / "evaluation" / "four_source_expansion" / "trial.json"
            out_md = root / "docs" / "trial.md"

            exit_code = module.main([
                "--sources",
                "nasa",
                "esa",
                "--limit",
                "2",
                "--dry-run",
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["phase"], "Phase 39")
            self.assertTrue(payload["dry_run"])
            self.assertEqual([item["source_id"] for item in payload["sources"]], ["nasa", "esa"])
            for item in payload["sources"]:
                self.assertLessEqual(item["limit"], 2)
                self.assertEqual(item["status"], "dry_run")
                self.assertFalse(item["network_attempted"])
                self.assertTrue(item["raw_only"])
                self.assertFalse(item["triples_write"])
                self.assertFalse(item["chroma_write"])
                self.assertFalse(item["neo4j_write"])
                self.assertTrue(item["active_source_unchanged"])
            self.assertFalse((root / "data").exists())
            self.assertIn("raw-only shadow ingest", out_md.read_text(encoding="utf-8"))

    def test_only_nasa_and_esa_are_allowed(self):
        module = load_module()

        report = module.build_trial(sources=["nasa", "wikidata", "zh_wikipedia", "esa"], limit=1, dry_run=True)

        self.assertEqual([item["source_id"] for item in report["sources"]], ["nasa", "esa"])
        self.assertEqual(report["skipped_sources"], ["wikidata", "zh_wikipedia"])

    def test_limit_defaults_to_20_and_can_be_smaller(self):
        module = load_module()

        default_report = module.build_trial(sources=["nasa"], dry_run=True)
        small_report = module.build_trial(sources=["nasa"], limit=3, dry_run=True)

        self.assertEqual(default_report["sources"][0]["limit"], 20)
        self.assertEqual(small_report["sources"][0]["limit"], 3)

    def test_network_failure_becomes_failed_report_not_crash(self):
        module = load_module()

        def failing_fetch(url, timeout=15):
            raise TimeoutError("offline")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_root = root / "data" / "raw_json"
            report = module.build_trial(
                root=ROOT,
                sources=["nasa"],
                limit=1,
                raw_root=raw_root,
                report_dir=root / "evaluation" / "four_source_expansion",
                fetcher=failing_fetch,
                dry_run=False,
            )

        item = report["sources"][0]
        self.assertEqual(item["status"], "completed_with_failures")
        self.assertEqual(item["failed"], 1)
        self.assertEqual(item["new_records"], 0)

    def test_script_source_has_no_downstream_or_destructive_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)
        self.assertNotIn("neo4j", source.lower().replace('"neo4j_write"', ""))
        self.assertNotIn("chroma", source.lower().replace('"chroma_write"', ""))
        self.assertNotIn("triples_dir", source.lower())


if __name__ == "__main__":
    unittest.main()

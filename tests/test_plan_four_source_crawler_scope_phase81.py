import json
import tempfile
import unittest
from pathlib import Path

from scripts import plan_four_source_crawler_scope_phase81 as phase81


class Phase81CrawlerScopeTests(unittest.TestCase):
    def test_limits_allowlist_and_dedup(self):
        rows = [
            {"title": "Mars", "url": "https://science.nasa.gov/mars", "_status": "review_needed"},
            {"title": "Mars", "url": "https://science.nasa.gov/mars", "_status": "review_needed"},
            {"title": "Rejected", "url": "https://science.nasa.gov/rejected", "_status": "rejected"},
            {"title": "Bad", "url": "https://example.com/bad", "_status": "review_needed"},
        ]
        report = phase81.dedup_and_classify("nasa", rows, 10)
        self.assertEqual(report["selected_candidates"], 2)
        self.assertEqual(report["review_needed"], 1)
        self.assertEqual(report["rejected"], 2)
        self.assertEqual(report["duplicates_excluded"], 1)
        self.assertEqual(report["allowlist_rejected"], 1)

    def test_output_path_restricted_to_repo_phase81_or_docs(self):
        self.assertTrue(phase81.output_allowed(phase81.ROOT / "evaluation" / "four_source_expansion" / "phase81" / "x.json"))
        self.assertTrue(phase81.output_allowed(phase81.ROOT / "docs" / "x.md", allow_docs=True))
        self.assertFalse(phase81.output_allowed(phase81.ROOT / "evaluation" / "four_source_expansion" / "x.json"))
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(phase81.output_allowed(Path(temp) / "docs" / "x.md", allow_docs=True))

    def test_build_report_does_not_write_data_and_keeps_source_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data" / "raw_json" / "zh_wikipedia").mkdir(parents=True)
            (root / "data" / "raw_json" / "zh_wikipedia" / "太阳.json").write_text(json.dumps({"title": "太阳"}), encoding="utf-8")
            out = root / "evaluation" / "four_source_expansion"
            out.mkdir(parents=True)
            (out / "nasa_frontier_refresh_phase58.json").write_text(json.dumps({"review_needed_candidates": [{"url": "science.nasa.gov/solar-system", "title": "Solar System"}]}), encoding="utf-8")
            (out / "esa_controlled_assessment_phase67.json").write_text(json.dumps({"candidate_statuses": [{"status": "review_needed", "url": "www.esa.int/science", "title": "ESA Science"}]}), encoding="utf-8")
            (out / "esa_raw_preview_batch_phase68.json").write_text(json.dumps({"candidate_statuses": []}), encoding="utf-8")
            (out / "wikidata_controlled_assessment_phase74.json").write_text(json.dumps({"candidate_statuses": [{"status": "accepted_for_package", "qid": "Q111", "title": "火星"}]}), encoding="utf-8")
            report = phase81.build_report(root)
            self.assertEqual(report["active_source"], "zh_wikipedia")
            self.assertEqual(report["registry"]["nasa"], "disabled")
            self.assertFalse(report["formal_default_triples_write"])
            self.assertFalse((root / "data" / "triples").exists())
            self.assertGreaterEqual(report["summary"]["candidate_count"], 4)


if __name__ == "__main__":
    unittest.main()

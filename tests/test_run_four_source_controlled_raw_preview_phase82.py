import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_four_source_controlled_raw_preview_phase82 as phase82


class Phase82RawPreviewTests(unittest.TestCase):
    def test_output_path_guard(self):
        self.assertTrue(phase82.output_allowed(phase82.ROOT / "evaluation" / "four_source_expansion" / "phase82" / "x.json"))
        self.assertTrue(phase82.output_allowed(phase82.ROOT / "docs" / "x.md", allow_docs=True))
        self.assertFalse(phase82.output_allowed(phase82.ROOT / "data" / "raw_json" / "x.json"))
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(phase82.output_allowed(Path(temp) / "docs" / "x.md", allow_docs=True))

    def test_dedup_limits_and_allowlist(self):
        rows = [
            {"source": "nasa", "title": "A", "id": "A", "url": "https://science.nasa.gov/a", "entity_id": "", "reason": "x"},
            {"source": "nasa", "title": "A", "id": "A", "url": "https://science.nasa.gov/a", "entity_id": "", "reason": "x"},
            {"source": "nasa", "title": "Bad", "id": "Bad", "url": "https://example.com/bad", "entity_id": "", "reason": "x"},
        ]
        selected, duplicates, rejected = phase82.dedup(rows, "nasa", 10)
        self.assertEqual(len(selected), 1)
        self.assertEqual(duplicates, 1)
        self.assertEqual(rejected, 1)

    def test_build_report_uses_evaluation_only_and_keeps_source_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            phase81 = root / "evaluation" / "four_source_expansion" / "phase81"
            phase81.mkdir(parents=True)
            (phase81 / "four_source_crawler_scope_expansion_phase81.json").write_text(json.dumps({"sources": {"zh_wikipedia": {"sample_candidates": [{"title": "太阳", "url": "https://zh.wikipedia.org/wiki/太阳"}]}}}), encoding="utf-8")
            (root / "data" / "raw_json" / "zh_wikipedia").mkdir(parents=True)
            (root / "data" / "raw_json" / "zh_wikipedia" / "太阳.json").write_text(json.dumps({"title": "太阳", "text": "太阳 raw"}), encoding="utf-8")
            fse = root / "evaluation" / "four_source_expansion"
            (fse / "nasa_frontier_refresh_phase58.json").write_text(json.dumps({"review_needed_candidates": [{"title": "Mars", "url": "science.nasa.gov/mars"}]}), encoding="utf-8")
            (fse / "esa_controlled_assessment_phase67.json").write_text(json.dumps({"candidate_statuses": []}), encoding="utf-8")
            (fse / "esa_raw_preview_batch_phase68.json").write_text(json.dumps({"candidate_statuses": []}), encoding="utf-8")
            (fse / "wikidata_controlled_assessment_phase74.json").write_text(json.dumps({"candidate_statuses": [{"status": "accepted_for_package", "title": "火星", "qid": "Q111"}]}), encoding="utf-8")
            with patch.object(phase82, "fetch_excerpt", return_value={"status_code": 200, "text_excerpt": "nasa raw"}):
                report = phase82.build_report(root)
            self.assertEqual(report["active_source"], "zh_wikipedia")
            self.assertEqual(report["registry"]["wikidata"], "disabled")
            self.assertFalse(report["formal_default_triples_write"])
            self.assertLessEqual(report["attempted"], 60)
            self.assertFalse((root / "data" / "triples").exists())

    def test_empty_raw_path_is_not_successful_local_preview(self):
        item = {"source": "wikidata", "title": "火星", "id": "Q111", "url": "https://www.wikidata.org/wiki/Q111", "entity_id": "Q111", "reason": "x", "assessment": {"qid": "Q111", "title": "火星"}}
        report = phase82.preview_item(item)
        self.assertEqual(report["status"], "assessment_preview")
        self.assertTrue(report["fetched"])


if __name__ == "__main__":
    unittest.main()

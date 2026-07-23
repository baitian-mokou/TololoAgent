import tempfile
import unittest
from pathlib import Path

from scripts import manual_review_closure_report_phase129 as phase129


class Phase129ManualReviewClosureReportTest(unittest.TestCase):
    def test_zh_and_esa_are_review_only_closed_not_production_ready(self):
        report = phase129.build_report()

        self.assertTrue(report["closures"]["zh_wikipedia"]["manual_review_closed"])
        self.assertEqual(report["closures"]["zh_wikipedia"]["closure_status"], "manual_review_closed_review_only")
        self.assertTrue(report["closures"]["esa"]["manual_review_closed"])
        self.assertEqual(report["closures"]["esa"]["closure_status"], "review_queue_closed_review_only")
        for source in ("zh_wikipedia", "esa"):
            self.assertFalse(report["closures"][source]["production_ready"])
            self.assertFalse(report["closures"][source]["queue_allowed"])

    def test_all_write_and_execution_flags_remain_false(self):
        report = phase129.build_report()

        for key in [
            "production_ready",
            "queue_allowed",
            "apply_allowed",
            "preflight_allowed",
            "ingest_allowed",
            "formal_default_triples_write",
            "chroma_write",
            "neo4j_write",
        ]:
            self.assertFalse(report[key], key)
        self.assertEqual(report["active_source"], "zh_wikipedia")
        self.assertTrue(report["active_source_unchanged"])

    def test_output_guard(self):
        self.assertTrue(phase129.output_allowed(phase129.REPORT_JSON))
        self.assertTrue(phase129.output_allowed(phase129.REPORT_MD, allow_docs=True))
        self.assertFalse(phase129.output_allowed(Path(tempfile.gettempdir()) / "phase129.json"))
        self.assertFalse(phase129.output_allowed(phase129.ROOT / "data" / "triples" / "x.json"))


if __name__ == "__main__":
    unittest.main()

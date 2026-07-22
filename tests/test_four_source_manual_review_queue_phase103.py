import tempfile
import unittest
from pathlib import Path

from scripts import four_source_manual_review_queue_phase103 as phase103


class Phase103ManualReviewQueueTest(unittest.TestCase):
    def test_queue_counts_and_pending_status(self):
        report = phase103.build_queue(
            phase102_report=phase103.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase102"
            / "four_source_review_closure_nasa_conditional_phase102.json",
            phase101_report=phase103.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase101"
            / "nasa_structured_review_sample_phase101.json",
            phase94_report=phase103.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase94"
            / "repaired_review_sample.json",
        )

        self.assertEqual(report["queue_count"], 27)
        self.assertEqual(report["queue_counts_by_source"], {"nasa": 5, "esa": 9, "zh_wikipedia": 3, "wikidata": 10})
        self.assertEqual({item["review_status"] for item in report["review_queue"]}, {"pending_manual_review"})
        self.assertFalse(report["shadow_apply_preflight_recommended"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertTrue(report["active_source_unchanged"])
        self.assertIn("NASA", report["checklist"]["source_specific_standards"])
        self.assertIn("Wikidata", report["checklist"]["source_specific_standards"])

    def test_output_guard_restricts_phase103_or_docs(self):
        self.assertFalse(phase103.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase103.output_allowed(phase103.ROOT / "evaluation" / "four_source_expansion" / "phase102" / "x.json"))
        self.assertTrue(phase103.output_allowed(phase103.ROOT / "evaluation" / "four_source_expansion" / "phase103" / "x.json"))
        self.assertTrue(phase103.output_allowed(phase103.ROOT / "docs" / "phase103.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

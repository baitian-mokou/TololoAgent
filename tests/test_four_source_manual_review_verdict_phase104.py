import tempfile
import unittest
from pathlib import Path

from scripts import four_source_manual_review_verdict_phase104 as phase104


class Phase104ManualReviewVerdictTest(unittest.TestCase):
    def test_verdict_filters_queue_and_keeps_safety_flags(self):
        report = phase104.build_verdict_report(
            phase103_queue=phase104.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase103"
            / "four_source_manual_review_queue_phase103.json"
        )

        self.assertEqual(report["overall_verdict"], "QUEUE_GO_WITH_CONDITIONS")
        self.assertEqual(report["filtered_count"], 20)
        self.assertEqual(report["rejected_count"], 7)
        self.assertEqual(report["filtered_counts_by_source"], {"nasa": 2, "esa": 8, "wikidata": 10})
        self.assertEqual(report["rejected_counts_by_source"], {"nasa": 3, "esa": 1, "zh_wikipedia": 3})
        self.assertEqual({item["review_status"] for item in report["filtered_review_queue"]}, {"accept_with_conditions"})
        self.assertEqual({item["review_status"] for item in report["rejected_queue"]}, {"reject_for_review"})
        filtered_ids = {(item["source"], item["title_or_id"]) for item in report["filtered_review_queue"]}
        rejected_ids = {(item["source"], item["title_or_id"]) for item in report["rejected_queue"]}
        self.assertFalse(filtered_ids & rejected_ids)
        self.assertTrue(report["shadow_review_only"])
        self.assertFalse(report["apply_preflight_allowed"])
        self.assertFalse(report["production_ready"])

    def test_output_guard_restricts_phase104_or_docs(self):
        self.assertFalse(phase104.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase104.output_allowed(phase104.ROOT / "evaluation" / "four_source_expansion" / "phase103" / "x.json"))
        self.assertTrue(phase104.output_allowed(phase104.ROOT / "evaluation" / "four_source_expansion" / "phase104" / "x.json"))
        self.assertTrue(phase104.output_allowed(phase104.ROOT / "docs" / "phase104.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

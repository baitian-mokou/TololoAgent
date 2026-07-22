import tempfile
import unittest
from pathlib import Path

from scripts import four_source_filtered_item_verdict_phase106 as phase106


class Phase106FilteredItemVerdictTest(unittest.TestCase):
    def test_all_filtered_items_are_conditional_and_review_only(self):
        report = phase106.build_item_verdict_report(
            phase104_report=phase106.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase104"
            / "verdict_report_phase104.json",
            phase105_handoff=phase106.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase105"
            / "review_handoff_phase105.json",
        )

        self.assertEqual(report["overall_verdict"], "FILTERED_ITEMS_GO_WITH_CONDITIONS")
        self.assertEqual(report["item_verdict_count"], 20)
        self.assertEqual(report["rejected_count"], 0)
        self.assertEqual(report["item_verdict_counts_by_source"], {"nasa": 2, "esa": 8, "wikidata": 10})
        self.assertEqual(report["item_verdict_counts_by_status"], {"ITEM_ACCEPT_WITH_CONDITIONS": 20})
        self.assertEqual({item["review_status"] for item in report["shadow_review_condition_queue"]}, {"accepted_with_conditions_for_shadow_review"})
        self.assertTrue(all(item["risk_label"] for item in report["shadow_review_condition_queue"]))
        self.assertFalse(report["apply_preflight_allowed"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])

    def test_risk_labels_are_source_specific(self):
        report = phase106.build_item_verdict_report(
            phase104_report=phase106.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase104"
            / "verdict_report_phase104.json",
            phase105_handoff=phase106.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase105"
            / "review_handoff_phase105.json",
        )
        by_source = {item["source"]: item["risk_label"] for item in report["shadow_review_condition_queue"]}

        self.assertIn("clean but thin", by_source["nasa"])
        self.assertIn("minor index/news risk", by_source["esa"])
        self.assertIn("valid but thin", by_source["wikidata"])

    def test_output_guard_restricts_phase106_or_docs(self):
        self.assertFalse(phase106.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase106.output_allowed(phase106.ROOT / "evaluation" / "four_source_expansion" / "phase105" / "x.json"))
        self.assertTrue(phase106.output_allowed(phase106.ROOT / "evaluation" / "four_source_expansion" / "phase106" / "x.json"))
        self.assertTrue(phase106.output_allowed(phase106.ROOT / "docs" / "phase106.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

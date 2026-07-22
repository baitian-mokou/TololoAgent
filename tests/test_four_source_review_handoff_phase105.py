import tempfile
import unittest
from pathlib import Path

from scripts import four_source_review_handoff_phase105 as phase105


class Phase105ReviewHandoffTest(unittest.TestCase):
    def test_handoff_counts_and_forbidden_flags(self):
        report = phase105.build_handoff(
            phase104_report=phase105.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase104"
            / "verdict_report_phase104.json"
        )

        self.assertEqual(report["overall_status"], "review_handoff_ready_approval_pending")
        self.assertEqual(report["filtered_count"], 20)
        self.assertEqual(report["rejected_count"], 7)
        self.assertEqual(report["filtered_counts_by_source"], {"nasa": 2, "esa": 8, "wikidata": 10})
        self.assertEqual(report["rejected_counts_by_source"], {"nasa": 3, "esa": 1, "zh_wikipedia": 3})
        self.assertEqual(report["human_reviewer_instructions"]["review_scope"], "review 20 filtered items only")
        self.assertIn("rejected 7 are out", report["human_reviewer_instructions"]["rejected_scope"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertTrue(report["shadow_review_only"])

    def test_filtered_queue_excludes_rejected_items(self):
        report = phase105.build_handoff(
            phase104_report=phase105.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase104"
            / "verdict_report_phase104.json"
        )
        filtered_ids = {(item["source"], item["title_or_id"]) for item in report["current_review_queue"]["filtered_items"]}
        rejected_ids = {(item["source"], item["title_or_id"]) for item in report["current_review_queue"]["rejected_items"]}

        self.assertEqual(len(filtered_ids), 20)
        self.assertEqual(len(rejected_ids), 7)
        self.assertFalse(filtered_ids & rejected_ids)

    def test_output_guard_restricts_phase105_or_docs(self):
        self.assertFalse(phase105.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase105.output_allowed(phase105.ROOT / "evaluation" / "four_source_expansion" / "phase104" / "x.json"))
        self.assertTrue(phase105.output_allowed(phase105.ROOT / "evaluation" / "four_source_expansion" / "phase105" / "x.json"))
        self.assertTrue(phase105.output_allowed(phase105.ROOT / "docs" / "phase105.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

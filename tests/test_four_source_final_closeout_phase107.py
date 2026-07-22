import tempfile
import unittest
from pathlib import Path

from scripts import four_source_final_closeout_phase107 as phase107


class Phase107FinalCloseoutTest(unittest.TestCase):
    def test_final_closeout_counts_and_flags(self):
        report = phase107.build_closeout(
            phase106_report=phase107.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase106"
            / "item_verdict_report_phase106.json",
            phase105_handoff=phase107.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase105"
            / "review_handoff_phase105.json",
            phase104_report=phase107.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase104"
            / "verdict_report_phase104.json",
        )

        self.assertEqual(report["final_verdict"], "four_source_review_only_closeout_complete_approval_pending")
        self.assertEqual(report["accepted_with_conditions_count"], 20)
        self.assertEqual(report["accepted_with_conditions_by_source"], {"nasa": 2, "esa": 8, "wikidata": 10})
        self.assertEqual(report["rejected_earlier_count"], 7)
        self.assertEqual(report["rejected_earlier_by_source"], {"nasa": 3, "esa": 1, "zh_wikipedia": 3})
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["formal_raw_write"])
        self.assertFalse(report["formal_default_triples_write"])

    def test_allowed_and_forbidden_next_steps_are_explicit(self):
        report = phase107.build_closeout(
            phase106_report=phase107.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase106"
            / "item_verdict_report_phase106.json",
            phase105_handoff=phase107.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase105"
            / "review_handoff_phase105.json",
            phase104_report=phase107.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase104"
            / "verdict_report_phase104.json",
        )

        self.assertIn("manual review of 20 filtered items", report["allowed_next_steps"])
        self.assertIn("apply", report["forbidden_next_steps_without_explicit_approval"])
        self.assertIn("shadow apply preflight", report["forbidden_next_steps_without_explicit_approval"])
        self.assertEqual(report["active_source"], "zh_wikipedia")
        self.assertTrue(report["active_source_unchanged"])

    def test_output_guard_restricts_phase107_or_docs(self):
        self.assertFalse(phase107.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase107.output_allowed(phase107.ROOT / "evaluation" / "four_source_expansion" / "phase106" / "x.json"))
        self.assertTrue(phase107.output_allowed(phase107.ROOT / "evaluation" / "four_source_expansion" / "phase107" / "x.json"))
        self.assertTrue(phase107.output_allowed(phase107.ROOT / "docs" / "phase107.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

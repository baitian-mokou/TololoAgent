import tempfile
import unittest
from pathlib import Path

from scripts import four_source_review_closure_phase102 as phase102


class Phase102FourSourceReviewClosureTest(unittest.TestCase):
    def test_closure_uses_phase101_nasa_and_keeps_preflight_false(self):
        report = phase102.build_closure(
            phase101_report=phase102.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase101"
            / "nasa_structured_review_sample_phase101.json",
            phase95_report=phase102.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase95"
            / "four_source_repaired_sample_quality_closure_phase95.json",
        )

        self.assertEqual(report["overall_verdict"], "four_source_manual_review_ready_approval_pending")
        self.assertEqual(report["source_statuses"]["nasa"]["verdict"], "manual_review_ready_conditional")
        self.assertEqual(report["source_statuses"]["nasa"]["sample_count"], 5)
        self.assertEqual(report["source_statuses"]["nasa"]["classes"]["strong_review_candidate"], 2)
        self.assertEqual(report["source_statuses"]["nasa"]["classes"]["conditional_review_candidate"], 3)
        self.assertEqual(report["source_statuses"]["wikidata"]["verdict"], "go_with_conditions_thin_entity_facts")
        self.assertEqual(report["source_statuses"]["zh_wikipedia"]["verdict"], "go_with_conditions_template_table_noise")
        self.assertEqual(report["source_statuses"]["esa"]["verdict"], "go_with_conditions_manual_review")
        self.assertFalse(report["shadow_apply_preflight_recommended"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertTrue(report["active_source_unchanged"])

    def test_output_guard_restricts_phase102_or_docs(self):
        self.assertFalse(phase102.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase102.output_allowed(phase102.ROOT / "evaluation" / "four_source_expansion" / "phase101" / "x.json"))
        self.assertTrue(phase102.output_allowed(phase102.ROOT / "evaluation" / "four_source_expansion" / "phase102" / "x.json"))
        self.assertTrue(phase102.output_allowed(phase102.ROOT / "docs" / "phase102.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from scripts import build_four_source_sample_quality_review_package_phase93 as phase93


class Phase93SampleQualityReviewPackageTest(unittest.TestCase):
    def test_review_package_preserves_32_samples_grouped_by_source_pending(self):
        package = phase93.build_review_package(
            expanded_sample_report=phase93.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase91"
            / "four_source_expanded_review_sample_gate_phase91.json",
            closure_report=phase93.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase92"
            / "four_source_review_sample_closure_phase92.json",
        )

        self.assertEqual(package["total_samples"], 32)
        self.assertEqual(package["sample_counts"], {"zh_wikipedia": 3, "nasa": 10, "esa": 9, "wikidata": 10})
        self.assertFalse(package["production_ready"])
        self.assertFalse(package["apply_approved"])
        self.assertFalse(package["ingest_approved"])
        self.assertEqual(set(package["samples_by_source"]), set(phase93.REQUIRED_SOURCES))
        for rows in package["samples_by_source"].values():
            for row in rows:
                self.assertEqual(row["review_status"], "pending_manual_or_reviewer_check")
                self.assertTrue(row["review_questions"])
                self.assertLessEqual(len(row["triples"]), 2)

    def test_output_guard_restricts_phase93_or_docs(self):
        self.assertFalse(phase93.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(
            phase93.output_allowed(
                phase93.ROOT / "evaluation" / "four_source_expansion" / "phase92" / "x.json"
            )
        )
        self.assertTrue(
            phase93.output_allowed(
                phase93.ROOT / "evaluation" / "four_source_expansion" / "phase93" / "x.json"
            )
        )
        self.assertTrue(phase93.output_allowed(phase93.ROOT / "docs" / "phase93.md", allow_docs=True))

    def test_rendered_package_does_not_claim_formal_approval(self):
        package = {
            "samples_by_source": {"nasa": []},
            "sample_counts": {"nasa": 0},
            "total_samples": 0,
            "production_ready": False,
            "apply_approved": False,
            "ingest_approved": False,
        }
        text = phase93.render_review_checklist(package).lower() + phase93.render_report(package).lower()
        self.assertIn("pending_manual_or_reviewer_check", text)
        self.assertNotIn("production ready", text)
        self.assertNotIn("apply approved", text)
        self.assertNotIn("ingest approved", text)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from scripts import nasa_structured_review_sample_phase101 as phase101


class Phase101NasaStructuredReviewSampleTest(unittest.TestCase):
    def test_builds_labels_from_phase100_candidates_only(self):
        report = phase101.build_review_sample(
            phase100_report=phase101.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase100"
            / "nasa_source_endpoint_strategy_preview_phase100.json"
        )

        self.assertEqual(report["input_phase"], "Phase100")
        self.assertEqual(report["sample_count"], 5)
        self.assertEqual(report["review_status"], "pending_manual_review")
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertTrue(report["active_source_unchanged"])
        self.assertIn("conditional_review_candidate", report["counts_by_quality_class"])
        self.assertIn("strong_review_candidate", report["counts_by_quality_class"])
        for row in report["review_samples"]:
            self.assertEqual(row["source_id"], "nasa")
            self.assertIn(row["quality_class"], {"strong_review_candidate", "conditional_review_candidate", "rejected_for_review"})
            self.assertTrue(row["endpoint"])
            self.assertTrue(row["method"])
            self.assertEqual(row["review_status"], "pending_manual_review")
            self.assertTrue(row["triples"])

    def test_quality_class_marks_images_cleaner_and_wp_rest_conditional(self):
        images = {"url": "https://images-assets.nasa.gov/image/PIA14414/collection.json", "body_excerpt": "Juno spacecraft at Jupiter."}
        wp = {"url": "https://science.nasa.gov/photojournal/example/", "body_excerpt": "Mapping Io Hidden Heat Photojournal NASA menu text."}

        self.assertEqual(phase101.quality_class(images)["quality_class"], "strong_review_candidate")
        self.assertEqual(phase101.quality_class(wp)["quality_class"], "conditional_review_candidate")

    def test_output_guard_restricts_phase101_or_docs(self):
        self.assertFalse(phase101.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase101.output_allowed(phase101.ROOT / "evaluation" / "four_source_expansion" / "phase100" / "x.json"))
        self.assertTrue(phase101.output_allowed(phase101.ROOT / "evaluation" / "four_source_expansion" / "phase101" / "x.json"))
        self.assertTrue(phase101.output_allowed(phase101.ROOT / "docs" / "phase101.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

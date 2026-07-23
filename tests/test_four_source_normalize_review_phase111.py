import tempfile
import unittest
from pathlib import Path

from scripts import four_source_normalize_review_phase111 as phase111


class Phase111NormalizeReviewPreviewTest(unittest.TestCase):
    def test_rejected_excluded_and_thin_not_strong(self):
        report = phase111.build_normalize_review(
            phase110_report=phase111.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase110"
            / "controlled_deeper_crawl_preview_phase110.json"
        )

        self.assertEqual(report["normalized_count"], 25)
        self.assertEqual(report["conditional_count"], 10)
        self.assertEqual(report["rejected_excluded"], 2)
        self.assertEqual(report["source_breakdown"], {"zh_wikipedia": 3, "nasa": 5, "esa": 7, "wikidata": 10})
        self.assertEqual({row["evidence_class"] for row in report["normalized_records"] if row["source"] == "wikidata"}, {"thin"})
        self.assertNotIn("strong_review", {row["review_status"] for row in report["normalized_records"] if row["evidence_class"] == "thin"})
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])

    def test_required_metadata_and_nonempty_preview_fields(self):
        report = phase111.build_normalize_review(
            phase110_report=phase111.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase110"
            / "controlled_deeper_crawl_preview_phase110.json"
        )

        for row in report["normalized_records"]:
            self.assertEqual(row["schema_version"], "phase111.normalize_review.v1")
            self.assertTrue(row["source"])
            self.assertTrue(row["source_url_or_entity"])
            self.assertTrue(row["provenance"]["phase110_url_or_entity"])
            self.assertTrue(row["quality_flags"])
            if row["evidence_class"] == "accepted":
                self.assertTrue(row["narrative"])
                self.assertTrue(row["triples_preview"])
            else:
                self.assertIn("thin_evidence_requires_review", row["risk_labels"])

    def test_output_guard_restricts_phase111_or_docs(self):
        self.assertFalse(phase111.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase111.output_allowed(phase111.ROOT / "evaluation" / "four_source_expansion" / "phase110" / "x.json"))
        self.assertTrue(phase111.output_allowed(phase111.ROOT / "evaluation" / "four_source_expansion" / "phase111" / "x.json"))
        self.assertTrue(phase111.output_allowed(phase111.ROOT / "docs" / "phase111.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

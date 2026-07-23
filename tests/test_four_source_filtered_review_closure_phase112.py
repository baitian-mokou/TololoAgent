import tempfile
import unittest
from pathlib import Path

from scripts import four_source_filtered_review_closure_phase112 as phase112


class Phase112FilteredReviewClosureTest(unittest.TestCase):
    def test_noise_detection_helpers(self):
        self.assertTrue(phase112.is_noise("<!doctype html><html><head><script>x</script></head>"))
        self.assertTrue(phase112.is_noise('{"source": "zh_wikipedia", "narrative_excerpt": "text"}'))
        self.assertTrue(phase112.is_noise('["http://example/a.jpg", "http://example/b.jpg"]'))
        self.assertTrue(phase112.is_noise("latest news index listing articles menu footer"))
        self.assertFalse(phase112.is_noise("Rosetta studied comet 67P during its mission with instruments and science observations."))

    def test_verdict_filters_noise_and_preserves_thin_conditionals(self):
        report = phase112.build_filtered_review(
            phase111_report=phase112.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase111"
            / "normalize_review_preview_phase111.json"
        )

        self.assertEqual(report["input_count"], 25)
        self.assertEqual(report["filtered_count"], 10)
        self.assertEqual(report["rejected_count"], 15)
        self.assertEqual(report["filtered_counts_by_source"], {"wikidata": 10})
        self.assertEqual(report["rejected_counts_by_source"], {"zh_wikipedia": 3, "nasa": 5, "esa": 7})
        self.assertEqual({row["review_status"] for row in report["filtered_queue"]}, {"ACCEPT_WITH_CONDITIONS"})
        self.assertEqual({row["evidence_class"] for row in report["filtered_queue"]}, {"thin"})
        self.assertTrue(all("thin_evidence_requires_review" in row["risk_labels"] for row in report["filtered_queue"]))
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])

    def test_rejected_records_are_excluded_from_filtered_queue(self):
        report = phase112.build_filtered_review(
            phase111_report=phase112.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase111"
            / "normalize_review_preview_phase111.json"
        )
        filtered_ids = {(row["source"], row["source_url_or_entity"]) for row in report["filtered_queue"]}
        rejected_ids = {(row["source"], row["source_url_or_entity"]) for row in report["rejected_queue"]}

        self.assertFalse(filtered_ids & rejected_ids)

    def test_output_guard_restricts_phase112_or_docs(self):
        self.assertFalse(phase112.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase112.output_allowed(phase112.ROOT / "evaluation" / "four_source_expansion" / "phase111" / "x.json"))
        self.assertTrue(phase112.output_allowed(phase112.ROOT / "evaluation" / "four_source_expansion" / "phase112" / "x.json"))
        self.assertTrue(phase112.output_allowed(phase112.ROOT / "docs" / "phase112.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

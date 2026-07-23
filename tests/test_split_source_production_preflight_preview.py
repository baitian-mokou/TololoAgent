import tempfile
import unittest
from pathlib import Path

from scripts import split_source_production_preflight_preview as preview


class SplitSourceProductionPreflightPreviewTest(unittest.TestCase):
    def test_source_verdicts_and_write_safety_flags(self):
        report = preview.build_report()

        self.assertEqual(report["source_verdicts"]["esa"], "manual_review_pending_not_production_ready")
        self.assertEqual(report["source_verdicts"]["nasa"], "conditional_not_strong_blocked")
        self.assertIn(report["source_verdicts"]["zh_wikipedia"], {"blocked_pending_diagnostics", "blocked_diagnostics_present"})
        self.assertEqual(report["source_verdicts"]["wikidata"], "thin_conditional_only")
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["formal_db_write_approved"])
        self.assertFalse(report["neo4j_write"])
        self.assertFalse(report["chroma_write"])
        self.assertFalse(report["formal_default_triples_write"])
        self.assertFalse(report["apply_allowed"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["ingest_allowed"])
        self.assertTrue(report["active_source_unchanged"])
        self.assertEqual(report["active_source"], "zh_wikipedia")

    def test_output_paths_are_docs_or_evaluation_only(self):
        self.assertTrue(preview.output_allowed(preview.REPORT_JSON))
        self.assertTrue(preview.output_allowed(preview.REPORT_MD))
        self.assertFalse(preview.output_allowed(Path(tempfile.gettempdir()) / "preview.json"))
        self.assertFalse(preview.output_allowed(preview.ROOT / "data" / "triples" / "x.json"))


if __name__ == "__main__":
    unittest.main()

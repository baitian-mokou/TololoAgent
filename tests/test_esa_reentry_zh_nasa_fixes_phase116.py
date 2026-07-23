import tempfile
import unittest
from pathlib import Path

from scripts import esa_reentry_zh_nasa_fixes_phase116 as phase116


class Phase116EsaReentryZhNasaFixesTest(unittest.TestCase):
    def test_esa_queue_count_and_pending_status(self):
        report = phase116.build_phase116()
        self.assertEqual(len(report["esa_reentry_queue"]), 3)
        self.assertTrue(all(row["review_status"] == "pending_manual_review" for row in report["esa_reentry_queue"]))
        self.assertTrue(all(row["apply_preflight_allowed"] is False for row in report["esa_reentry_queue"]))

    def test_nasa_conditional_not_strong(self):
        report = phase116.build_phase116()
        nasa = report["nasa_conditional_fix_preview"]
        self.assertEqual(nasa["conditional_count"], 1)
        self.assertEqual(nasa["strong_count"], 0)
        self.assertIn("conditional_not_strong", nasa["quality_labels"])

    def test_zh_fetch_failures_are_blocker(self):
        report = phase116.build_phase116()
        zh = report["zh_strategy_fix_preview"]
        self.assertEqual(zh["failed_count"], 3)
        self.assertEqual(zh["status"], "blocked_needs_mediawiki_fetch_encoding_fix")
        self.assertFalse(zh["auto_queue_allowed"])

    def test_flags_and_output_guard(self):
        report = phase116.build_phase116()
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertFalse(phase116.output_allowed(Path(tempfile.gettempdir()) / "phase116.json"))
        self.assertFalse(phase116.output_allowed(phase116.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase116.output_allowed(phase116.ROOT / "evaluation" / "four_source_expansion" / "phase116" / "x.json"))
        self.assertTrue(phase116.output_allowed(phase116.ROOT / "docs" / "phase116.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from scripts import run_four_source_expanded_review_sample_gate_phase91 as phase91


class Phase91ExpandedReviewSampleGateTest(unittest.TestCase):
    def test_expanded_sample_balances_sources_and_stays_pending(self):
        report = phase91.build_report(
            package_report=phase91.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase87"
            / "four_source_rebuilt_pending_shadow_package_phase87.json",
            closure_report=phase91.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase90"
            / "four_source_review_sample_quality_closure_phase90.json",
            per_source_limit=10,
        )

        self.assertEqual(report["sample_counts"], {"zh_wikipedia": 3, "nasa": 10, "esa": 9, "wikidata": 10})
        self.assertEqual(report["total_samples"], 32)
        self.assertTrue(report["sample_quality_pass"])
        self.assertEqual(report["blocking_findings"], [])
        self.assertEqual(report["warnings"], [])
        self.assertFalse(report["production_ready"])
        self.assertEqual(report["approval_status"], "pending_review")
        self.assertEqual(report["closure_verdict"], "shadow_review_ready_approval_pending")
        self.assertTrue(report["active_source_unchanged"])
        self.assertEqual(report["registry"]["wikidata"], "disabled")
        self.assertFalse(report["formal_default_triples_write"])
        for row in report["samples"]["nasa"]:
            self.assertTrue(phase91.nasa_repair_marker_ok(row))
            self.assertTrue(row["title"])
            self.assertTrue(row["source_url"])

    def test_quality_gate_blocks_duplicate_or_missing_fields(self):
        row = {
            "source": "nasa",
            "title": "x",
            "source_url": "u",
            "metadata": {"schema_version": "v", "quality_flags": {"metadata_repaired": True}},
            "provenance": {},
            "triples": [],
            "narrative": {},
            "review_status": "pending",
        }
        findings, warnings = phase91.check_quality({"nasa": [row, dict(row)]})
        self.assertIn("source_balance_missing", findings)
        self.assertIn("duplicate_sample", findings)
        self.assertIn("sample_missing_triple_or_narrative", findings)
        self.assertIn("nasa_repair_marker_missing", warnings)

    def test_output_guard_restricts_phase91_or_docs(self):
        self.assertFalse(phase91.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(
            phase91.output_allowed(
                phase91.ROOT / "evaluation" / "four_source_expansion" / "phase90" / "x.json"
            )
        )
        self.assertTrue(
            phase91.output_allowed(
                phase91.ROOT / "evaluation" / "four_source_expansion" / "phase91" / "x.json"
            )
        )
        self.assertTrue(phase91.output_allowed(phase91.ROOT / "docs" / "phase91.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

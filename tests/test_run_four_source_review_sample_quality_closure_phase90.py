import tempfile
import unittest
from pathlib import Path

from scripts import run_four_source_review_sample_quality_closure_phase90 as phase90


class Phase90ReviewSampleQualityClosureTest(unittest.TestCase):
    def test_quality_gate_passes_current_sample_but_stays_non_production(self):
        report = phase90.build_closure(
            sample_report=phase90.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase89"
            / "four_source_shadow_review_preview_phase89.json",
            package_report=phase90.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase87"
            / "four_source_rebuilt_pending_shadow_package_phase87.json",
            gate_report=phase90.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase88"
            / "four_source_rebuilt_readiness_gate_phase88.json",
        )

        self.assertTrue(report["sample_quality_pass"])
        self.assertEqual(report["blocking_findings"], [])
        self.assertEqual(report["approval_status"], "pending_review")
        self.assertFalse(report["production_ready"])
        self.assertEqual(report["closure_verdict"], "shadow_review_ready_approval_pending")
        self.assertEqual(report["sample_counts"], {source: 3 for source in phase90.REQUIRED_SOURCES})
        self.assertTrue(report["active_source_unchanged"])
        self.assertEqual(report["registry"]["nasa"], "disabled")
        self.assertFalse(report["formal_default_triples_write"])
        self.assertNotIn("approved_for_shadow_write", " ".join(report["next_recommendations"]))

    def test_quality_gate_blocks_missing_required_sample_fields(self):
        bad = {
            "review_only": True,
            "review_status": "pending",
            "production_ready": False,
            "approval_status": "pending_review",
            "nasa_repair_marker": "title_or_excerpt",
            "samples": {"nasa": [{"source": "nasa", "title": "", "source_url": "", "metadata": {}, "provenance": {}, "triples": [], "narratives": [], "review_status": "pending"}]},
        }
        findings, warnings = phase90.check_sample_quality(bad)
        self.assertIn("missing_required_sample_fields", findings)
        self.assertIn("source_balance_missing", findings)
        self.assertIn("nasa_repair_marker_missing_on_sample", warnings)

    def test_output_guard_and_render_do_not_grant_production(self):
        self.assertFalse(phase90.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(
            phase90.output_allowed(
                phase90.ROOT / "evaluation" / "four_source_expansion" / "phase89" / "x.json"
            )
        )
        self.assertTrue(
            phase90.output_allowed(
                phase90.ROOT / "evaluation" / "four_source_expansion" / "phase90" / "x.json"
            )
        )
        text = phase90.render_md(
            {
                "sample_quality_pass": True,
                "production_ready": False,
                "approval_status": "pending_review",
                "closure_verdict": "shadow_review_ready_approval_pending",
                "sample_counts": {source: 3 for source in phase90.REQUIRED_SOURCES},
                "blocking_findings": [],
                "warnings": [],
                "next_recommendations": ["manual review of samples"],
            }
        )
        self.assertNotIn("production ready", text.lower())
        self.assertIn("shadow-review ready", text.lower())


if __name__ == "__main__":
    unittest.main()

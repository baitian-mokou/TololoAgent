import tempfile
import unittest
from pathlib import Path

from scripts import run_four_source_review_sample_closure_phase92 as phase92


class Phase92ReviewSampleClosureTest(unittest.TestCase):
    def test_closure_summarizes_phase91_without_formal_authorization(self):
        report = phase92.build_closure(
            expanded_sample_report=phase92.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase91"
            / "four_source_expanded_review_sample_gate_phase91.json",
            package_report=phase92.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase87"
            / "four_source_rebuilt_pending_shadow_package_phase87.json",
            readiness_report=phase92.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase88"
            / "four_source_rebuilt_readiness_gate_phase88.json",
            prior_closure_report=phase92.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase90"
            / "four_source_review_sample_quality_closure_phase90.json",
        )

        self.assertEqual(report["closure_verdict"], "sample_review_ready_approval_pending")
        self.assertEqual(report["sample_counts"], {"zh_wikipedia": 3, "nasa": 10, "esa": 9, "wikidata": 10})
        self.assertEqual(report["total_samples"], 32)
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertEqual(report["registry"]["esa"], "disabled")
        self.assertTrue(report["active_source_unchanged"])
        self.assertIn("manual sample quality review", report["next_recommendations"])
        self.assertNotIn("approved_for_shadow_write", " ".join(report["next_recommendations"]))
        self.assertFalse(report["formal_default_triples_write"])

    def test_output_guard_restricts_phase92_or_docs(self):
        self.assertFalse(phase92.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(
            phase92.output_allowed(
                phase92.ROOT / "evaluation" / "four_source_expansion" / "phase91" / "x.json"
            )
        )
        self.assertTrue(
            phase92.output_allowed(
                phase92.ROOT / "evaluation" / "four_source_expansion" / "phase92" / "x.json"
            )
        )
        self.assertTrue(phase92.output_allowed(phase92.ROOT / "docs" / "phase92.md", allow_docs=True))

    def test_render_does_not_claim_production_ready_or_apply_approved(self):
        text = phase92.render_md(
            {
                "closure_verdict": "sample_review_ready_approval_pending",
                "production_ready": False,
                "sample_counts": {"zh_wikipedia": 3, "nasa": 10, "esa": 9, "wikidata": 10},
                "total_samples": 32,
                "remaining_risks": ["manual review still required"],
                "next_recommendations": ["manual sample quality review"],
            }
        ).lower()
        self.assertIn("sample-review ready", text)
        self.assertNotIn("production ready", text)
        self.assertNotIn("apply approved", text)
        self.assertNotIn("ingest approved", text)


if __name__ == "__main__":
    unittest.main()

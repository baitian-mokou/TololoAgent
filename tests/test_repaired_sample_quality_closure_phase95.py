import tempfile
import unittest
from pathlib import Path

from scripts import repaired_sample_quality_closure_phase95 as phase95


class Phase95ClosureTest(unittest.TestCase):
    def test_verdicts_are_conservative_and_nasa_blocks_preflight(self):
        report = phase95.build_closure(
            phase94_report=phase95.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase94"
            / "four_source_sample_content_quality_repair_phase94.json",
            phase93_report=phase95.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase93"
            / "four_source_sample_quality_review_package_phase93.json",
            phase92_report=phase95.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase92"
            / "four_source_review_sample_closure_phase92.json",
        )

        self.assertEqual(report["source_verdicts"]["esa"], "reviewable_candidate")
        self.assertEqual(report["source_verdicts"]["zh_wikipedia"], "reviewable_with_template_noise")
        self.assertEqual(report["source_verdicts"]["wikidata"], "reviewable_thin_facts_needs_enrichment")
        self.assertEqual(report["source_verdicts"]["nasa"], "no_go_current_samples_rejected")
        self.assertEqual(report["overall_verdict"], "partial_source_review_ready_nasa_blocked")
        self.assertFalse(report["shadow_apply_preflight_recommended"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["formal_raw_write"])
        self.assertFalse(report["formal_default_triples_write"])
        self.assertTrue(report["active_source_unchanged"])

    def test_output_guard_restricts_phase95_or_docs(self):
        self.assertFalse(phase95.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(
            phase95.output_allowed(
                phase95.ROOT / "evaluation" / "four_source_expansion" / "phase94" / "x.json"
            )
        )
        self.assertTrue(
            phase95.output_allowed(
                phase95.ROOT / "evaluation" / "four_source_expansion" / "phase95" / "x.json"
            )
        )
        self.assertTrue(phase95.output_allowed(phase95.ROOT / "docs" / "phase95.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

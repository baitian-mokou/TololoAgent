import tempfile
import unittest
from pathlib import Path

from scripts import four_source_repair_preview_phase108 as phase108


class Phase108SourceRepairPreviewTest(unittest.TestCase):
    def test_text_filters_and_enrichment_helpers(self):
        zh_text = "{| class='infobox'\n| mass = 1\n|}\n'''太阳'''是太阳系中心的恒星。它提供光和热。"
        self.assertEqual(phase108.clean_zh_text(zh_text), "太阳是太阳系中心的恒星。它提供光和热。")
        self.assertTrue(phase108.is_esa_index_page("ESA - Space Science", "news index listing latest articles missions"))
        self.assertFalse(phase108.is_esa_index_page("ESA - Rosetta", "Rosetta studied comet 67P during its mission."))
        self.assertEqual(
            phase108.enrich_wikidata_fact({"title_or_id": "Q123 Sun", "url_or_entity": "Q123"}),
            "Q123 Sun is a Wikidata entity with source reference Q123.",
        )

    def test_repair_preview_counts_and_flags(self):
        report = phase108.build_repair_preview(
            phase104_report=phase108.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase104"
            / "verdict_report_phase104.json",
            phase107_closeout=phase108.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase107"
            / "final_closeout_phase107.json",
        )

        self.assertEqual(report["overall_status"], "source_repair_preview_ready_for_review")
        self.assertEqual(report["repair_counts_by_source"]["zh_wikipedia"], {"repaired_candidates": 0, "rejected_remaining": 3})
        self.assertEqual(report["repair_counts_by_source"]["esa"], {"repaired_candidates": 0, "conditional_preserved": 8, "rejected_remaining": 1})
        self.assertEqual(report["repair_counts_by_source"]["nasa"], {"conditional_preserved": 2, "rejected_remaining": 3})
        self.assertEqual(report["repair_counts_by_source"]["wikidata"], {"repaired_candidates": 10, "conditional_preserved": 10})
        self.assertEqual(report["readiness_for_deeper_crawl_gate"], "ready_for_controlled_deeper_crawl_gate_with_review")
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertFalse(report["preflight_allowed"])

    def test_output_guard_restricts_phase108_or_docs(self):
        self.assertFalse(phase108.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase108.output_allowed(phase108.ROOT / "evaluation" / "four_source_expansion" / "phase107" / "x.json"))
        self.assertTrue(phase108.output_allowed(phase108.ROOT / "evaluation" / "four_source_expansion" / "phase108" / "x.json"))
        self.assertTrue(phase108.output_allowed(phase108.ROOT / "docs" / "phase108.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

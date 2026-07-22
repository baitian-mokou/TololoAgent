import tempfile
import unittest
from pathlib import Path

from scripts import repair_four_source_review_package_phase94 as phase94


class Phase94ReviewPackageRepairTest(unittest.TestCase):
    def test_repairs_wikidata_json_and_nasa_boilerplate_without_approval(self):
        report = phase94.build_repaired_package(
            review_package=phase94.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase93"
            / "review_sample.json",
            phase87_package=phase94.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase87"
            / "four_source_rebuilt_pending_shadow_package_phase87.json",
        )

        self.assertFalse(report["production_ready"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertEqual(report["review_status"], "pending_manual_or_reviewer_check")
        self.assertEqual(report["counts_by_source"]["wikidata"]["repaired"], 10)
        self.assertEqual(report["counts_by_source"]["nasa"]["repaired"], 0)
        self.assertEqual(report["counts_by_source"]["nasa"]["rejected"], 10)
        self.assertEqual(report["counts_by_source"]["esa"]["preserved"], 9)
        self.assertEqual(report["counts_by_source"]["zh_wikipedia"]["preserved"], 3)
        for row in report["samples_by_source"]["wikidata"]:
            self.assertFalse(row["narrative_excerpt"].lstrip().startswith("{"))
            self.assertNotEqual(row["triples"][0]["predicate"], "HAS_PREVIEW_TEXT")
        for row in report["samples_by_source"]["nasa"]:
            self.assertEqual(row["review_status"], "rejected_for_review")
            self.assertIn(
                row["rejection_reason"],
                {"nasa_boilerplate_only_after_cleaning", "nasa_navigation_residue_after_cleaning"},
            )
            self.assertEqual(row["narrative_excerpt"], "")
            self.assertEqual(row["triples"], [])

    def test_clean_nasa_boilerplate_rejects_if_no_content_left(self):
        self.assertEqual(phase94.clean_nasa_text("NASA Explore Search News & Events NASA+ Podcasts Multimedia"), "")
        self.assertTrue(
            phase94.is_nasa_navigation_residue(
                "Solar System Exploration Images Expedition 64 Mars perseverance SpaceX Crew-2 "
                "International Space Station Home Missions Humans in Space Earth"
            )
        )

    def test_output_guard_restricts_phase94_or_docs(self):
        self.assertFalse(phase94.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(
            phase94.output_allowed(
                phase94.ROOT / "evaluation" / "four_source_expansion" / "phase93" / "x.json"
            )
        )
        self.assertTrue(
            phase94.output_allowed(
                phase94.ROOT / "evaluation" / "four_source_expansion" / "phase94" / "x.json"
            )
        )
        self.assertTrue(phase94.output_allowed(phase94.ROOT / "docs" / "phase94.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

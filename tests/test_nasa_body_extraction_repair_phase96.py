import tempfile
import unittest
from pathlib import Path

from scripts import nasa_body_extraction_repair_phase96 as phase96


class Phase96NasaBodyExtractionRepairTest(unittest.TestCase):
    def test_rejects_navigation_residue_and_accepts_content_fixture_without_writes(self):
        nav = {
            "source": "nasa",
            "title": "Solar System Exploration",
            "url": "https://science.nasa.gov/solar-system",
            "status": "http_200",
            "text_excerpt": "Solar System Exploration Images Expedition 64 Mars perseverance SpaceX Crew-2 "
            "International Space Station View All Topics A-Z Home Missions Humans in Space Earth",
        }
        content = {
            "source": "nasa",
            "title": "Juno",
            "url": "https://science.nasa.gov/mission/juno",
            "status": "http_200",
            "text_excerpt": "Juno is a NASA spacecraft orbiting Jupiter. The mission studies Jupiter's "
            "atmosphere, magnetic field, gravity field, and polar regions to understand the planet's origin.",
        }

        report = phase96.build_preview(raw_previews=[nav, content])

        self.assertEqual(report["candidate_count"], 2)
        self.assertEqual(report["accepted_reviewable"], 1)
        self.assertEqual(report["rejected_search_or_nav"], 1)
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["formal_raw_write"])
        self.assertFalse(report["formal_default_triples_write"])
        self.assertTrue(report["active_source_unchanged"])
        accepted = report["reviewable_samples"][0]
        self.assertEqual(accepted["title"], "Juno")
        self.assertIn("studies Jupiter", accepted["narrative"])
        self.assertEqual(accepted["triples"][0]["predicate"], "SOURCE_URL")

    def test_phase82_inputs_block_when_no_reviewable_body_exists(self):
        report = phase96.build_preview_from_phase82(
            phase82_report=phase96.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase82"
            / "four_source_controlled_raw_preview_phase82.json"
        )

        self.assertEqual(report["accepted_reviewable"], 0)
        self.assertTrue(report["needs_live_refetch"])
        self.assertEqual(report["quality_verdict"], "nasa_body_extraction_blocked_needs_better_raw")

    def test_output_guard_restricts_phase96_or_docs(self):
        self.assertFalse(phase96.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(
            phase96.output_allowed(
                phase96.ROOT / "evaluation" / "four_source_expansion" / "phase95" / "x.json"
            )
        )
        self.assertTrue(
            phase96.output_allowed(
                phase96.ROOT / "evaluation" / "four_source_expansion" / "phase96" / "x.json"
            )
        )
        self.assertTrue(phase96.output_allowed(phase96.ROOT / "docs" / "phase96.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

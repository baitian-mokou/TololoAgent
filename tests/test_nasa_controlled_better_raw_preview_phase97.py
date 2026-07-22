import tempfile
import unittest
from pathlib import Path

from scripts import nasa_controlled_better_raw_preview_phase97 as phase97


class Phase97NasaControlledBetterRawPreviewTest(unittest.TestCase):
    def test_selects_allowed_non_gallery_urls_with_limit(self):
        rows = [
            {"source_id": "nasa", "url": "https://science.nasa.gov/search?q=mars"},
            {"source_id": "nasa", "url": "https://science.nasa.gov/gallery/mars"},
            {"source_id": "nasa", "url": "https://science.nasa.gov/mission/juno"},
            {"source_id": "nasa", "url": "https://evil.example/nasa"},
            {"source_id": "nasa", "url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet"},
        ]

        selected = phase97.select_candidates(rows, limit=2)

        self.assertEqual([row["url"] for row in selected], [
            "https://science.nasa.gov/mission/juno",
            "https://nssdc.gsfc.nasa.gov/planetary/factsheet",
        ])

    def test_body_extraction_accepts_article_fixture_and_rejects_nav_fixture(self):
        article = """
        <html><head><title>Juno</title></head><body><main>
        <h1>Juno</h1><p>Juno is a NASA spacecraft orbiting Jupiter. The mission studies
        Jupiter's atmosphere, magnetic field, gravity field, and polar regions to understand
        the planet's origin and evolution.</p></main></body></html>
        """
        nav = "<html><body>Explore Search News & Events Images Expedition SpaceX Crew Home Missions</body></html>"

        self.assertIn("mission studies", phase97.extract_body(article).lower())
        self.assertEqual(phase97.extract_body(nav), "")

    def test_build_report_keeps_no_write_flags_and_no_production_approval(self):
        selected = [{"source_id": "nasa", "url": "https://science.nasa.gov/mission/juno", "title": "Juno"}]
        fetched = [{
            "url": selected[0]["url"],
            "status": "http_200",
            "status_code": 200,
            "html": "<main>Juno is a NASA spacecraft orbiting Jupiter. The mission studies Jupiter and its atmosphere.</main>",
        }]

        report = phase97.build_report(selected=selected, fetched=fetched, live_fetch_used=True)

        self.assertEqual(report["attempted"], 1)
        self.assertEqual(report["succeeded"], 1)
        self.assertEqual(report["accepted_reviewable"], 1)
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["formal_raw_write"])
        self.assertFalse(report["formal_default_triples_write"])
        self.assertTrue(report["active_source_unchanged"])

    def test_output_guard_restricts_phase97_or_docs(self):
        self.assertFalse(phase97.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase97.output_allowed(phase97.ROOT / "evaluation" / "four_source_expansion" / "phase96" / "x.json"))
        self.assertTrue(phase97.output_allowed(phase97.ROOT / "evaluation" / "four_source_expansion" / "phase97" / "x.json"))
        self.assertTrue(phase97.output_allowed(phase97.ROOT / "docs" / "phase97.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

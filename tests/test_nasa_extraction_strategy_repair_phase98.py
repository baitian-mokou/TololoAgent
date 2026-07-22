import tempfile
import unittest
from pathlib import Path

from scripts import nasa_extraction_strategy_repair_phase98 as phase98


class Phase98NasaExtractionStrategyRepairTest(unittest.TestCase):
    def test_extracts_meta_and_json_ld_candidates(self):
        page = """
        <html><head>
        <meta name="description" content="Juno is a NASA mission studying Jupiter's atmosphere and magnetic field.">
        <script type="application/ld+json">{"name":"Juno","description":"Juno is a spacecraft orbiting Jupiter to study the planet's origin and evolution."}</script>
        </head><body><nav>Explore Search News Events</nav></body></html>
        """

        candidates = phase98.extraction_candidates(page)
        accepted = [item for item in candidates if item["accepted"]]

        self.assertTrue(any(item["method"] == "json_ld_description" for item in accepted))
        self.assertTrue(any(item["method"] == "meta_description" for item in accepted))

    def test_rejects_boilerplate_and_keeps_phase97_url_set(self):
        page = "<html><body><main>Explore Search Images Expedition SpaceX Crew Home Missions</main></body></html>"
        candidates = phase98.extraction_candidates(page)

        self.assertFalse(any(item["accepted"] for item in candidates))
        self.assertEqual(
            phase98.phase97_urls({
                "selected_urls": [
                    "https://nssdc.gsfc.nasa.gov/planetary/factsheet",
                    "https://science.nasa.gov/mission/juno",
                ]
            }),
            [
                "https://nssdc.gsfc.nasa.gov/planetary/factsheet",
                "https://science.nasa.gov/mission/juno",
            ],
        )

    def test_report_has_no_production_or_formal_writes(self):
        fetched = [{
            "url": "https://science.nasa.gov/mission/juno",
            "status": "http_200",
            "status_code": 200,
            "html": "<script type=\"application/ld+json\">{\"name\":\"Juno\",\"articleBody\":\"Juno is a NASA mission studying Jupiter's atmosphere, magnetosphere, gravity, and origin.\"}</script>",
        }]

        report = phase98.build_report(urls=[fetched[0]["url"]], fetched=fetched, live_refetch_used=True)

        self.assertEqual(report["attempted"], 1)
        self.assertEqual(report["accepted"], 1)
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["formal_raw_write"])
        self.assertFalse(report["formal_default_triples_write"])
        self.assertTrue(report["active_source_unchanged"])

    def test_output_guard_restricts_phase98_or_docs(self):
        self.assertFalse(phase98.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase98.output_allowed(phase98.ROOT / "evaluation" / "four_source_expansion" / "phase97" / "x.json"))
        self.assertTrue(phase98.output_allowed(phase98.ROOT / "evaluation" / "four_source_expansion" / "phase98" / "x.json"))
        self.assertTrue(phase98.output_allowed(phase98.ROOT / "docs" / "phase98.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

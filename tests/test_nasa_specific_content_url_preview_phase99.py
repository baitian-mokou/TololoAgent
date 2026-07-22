import tempfile
import unittest
from pathlib import Path

from scripts import nasa_specific_content_url_preview_phase99 as phase99


class Phase99NasaSpecificContentUrlPreviewTest(unittest.TestCase):
    def test_specific_url_filter_keeps_official_content_pages_only(self):
        urls = [
            "https://science.nasa.gov/search?q=juno",
            "https://science.nasa.gov/gallery/juno",
            "https://science.nasa.gov/mission/juno",
            "https://science.nasa.gov/mission/juno/overview/",
            "https://science.nasa.gov/solar-system/planets/mars/facts/",
            "https://example.com/mission/juno",
        ]

        self.assertEqual(
            phase99.select_specific_urls(urls, limit=10),
            [
                "https://science.nasa.gov/mission/juno",
                "https://science.nasa.gov/mission/juno/overview/",
                "https://science.nasa.gov/solar-system/planets/mars/facts/",
            ],
        )

    def test_meta_only_is_thin_and_body_or_jsonld_article_body_is_strong(self):
        meta_only = '<meta name="description" content="Juno is a NASA mission studying Jupiter and its atmosphere.">'
        body = "<main><p>Juno is a NASA mission studying Jupiter and its atmosphere, magnetosphere, gravity, and origin.</p></main>"
        jsonld = '<script type="application/ld+json">{"articleBody":"Cassini was a NASA mission that studied Saturn, its rings, moons, atmosphere, and magnetosphere."}</script>'

        self.assertEqual(phase99.classify_page(meta_only)["status"], "thin_evidence_review_candidate")
        self.assertEqual(phase99.classify_page(body)["status"], "strong_accepted")
        self.assertEqual(phase99.classify_page(jsonld)["status"], "strong_accepted")

    def test_build_report_has_no_production_or_formal_writes(self):
        fetched = [{
            "url": "https://science.nasa.gov/mission/juno",
            "status": "http_200",
            "status_code": 200,
            "html": "<main>Juno is a NASA mission studying Jupiter and its atmosphere, magnetosphere, gravity, and origin.</main>",
        }]

        report = phase99.build_report(urls=[fetched[0]["url"]], fetched=fetched, live_fetch_used=True)

        self.assertEqual(report["attempted"], 1)
        self.assertEqual(report["strong_accepted"], 1)
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["formal_raw_write"])
        self.assertFalse(report["formal_default_triples_write"])
        self.assertTrue(report["active_source_unchanged"])

    def test_output_guard_restricts_phase99_or_docs(self):
        self.assertFalse(phase99.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase99.output_allowed(phase99.ROOT / "evaluation" / "four_source_expansion" / "phase98" / "x.json"))
        self.assertTrue(phase99.output_allowed(phase99.ROOT / "evaluation" / "four_source_expansion" / "phase99" / "x.json"))
        self.assertTrue(phase99.output_allowed(phase99.ROOT / "docs" / "phase99.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

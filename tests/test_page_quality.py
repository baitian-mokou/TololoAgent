import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from src.source_quality.page_quality import score_page


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "score_candidate_pages.py"


def load_script():
    spec = importlib.util.spec_from_file_location("score_candidate_pages", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PageQualityTests(unittest.TestCase):
    def test_nasa_fact_table_is_accepted(self):
        result = score_page({
            "url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
            "title": "Mars Fact Sheet",
            "html": """
                <html><body><h1>Mars Fact Sheet</h1>
                <table><tr><th>Mass</th><td>0.64171 10^24 kg</td></tr><tr><th>Radius</th><td>3389.5 km</td></tr></table>
                <p>Mars is a planet in the solar system with atmosphere, orbit, diameter, mass and mission data.</p>
                <p>Reference: NASA Planetary Fact Sheet.</p></body></html>
            """,
        })

        self.assertEqual(result["triage"], "accepted")
        self.assertIn("official_source", result["labels"])
        self.assertIn("fact_page", result["labels"])
        self.assertIn("has_table", result["labels"])

    def test_esa_mission_page_is_accepted_or_exploratory(self):
        result = score_page({
            "url": "https://www.esa.int/Science_Exploration/Space_Science/Juice",
            "title": "Juice mission overview",
            "text": "Juice is an ESA spacecraft mission to Jupiter and its icy moons. The mission studies Ganymede, Europa, Callisto, orbit, instruments, science objectives and planetary environment.",
        })

        self.assertIn(result["triage"], {"accepted", "exploratory"})
        self.assertIn("mission_page", result["labels"])
        self.assertIn("science_topic", result["labels"])

    def test_science_news_is_exploratory(self):
        result = score_page({
            "url": "https://science.example.edu/news/mars-water-update",
            "title": "New Mars water research update",
            "text": "Researchers report new observations about Mars water ice and planetary science. The article explains evidence, mission context, and links to research references.",
        })

        self.assertEqual(result["triage"], "exploratory")
        self.assertIn("news_page", result["labels"])

    def test_gallery_and_search_pages_are_rejected(self):
        gallery = score_page({
            "url": "https://science.nasa.gov/gallery/mars-images/",
            "title": "Mars image gallery",
            "text": "Images and videos from Mars.",
        })
        search = score_page({
            "url": "https://www.esa.int/Search?search=Jupiter",
            "title": "Search results",
            "text": "Search results for Jupiter mission pages.",
        })

        self.assertEqual(gallery["triage"], "rejected")
        self.assertIn("media_page", gallery["labels"])
        self.assertEqual(search["triage"], "rejected")
        self.assertIn("search_page", search["labels"])

    def test_nasa_fact_sheet_survives_navigation_media_noise(self):
        noisy_text = (
            "NASA Space Science Data Coordinated Archive Status. "
            "Mercury planet factsheet mass radius diameter orbit atmosphere planetary science reference. "
            "Navigation links: news media gallery images videos stories update. "
        ) * 20
        result = score_page({
            "url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/mercuryfact.html",
            "title": "Mercury Fact Sheet",
            "text": noisy_text,
        })

        self.assertIn(result["triage"], {"accepted", "review_needed"})
        self.assertNotEqual(result["triage"], "rejected")

    def test_esa_mission_page_survives_navigation_media_noise(self):
        noisy_text = (
            "ESA Juice mission overview spacecraft Jupiter icy moons science objectives instruments. "
            "Navigation links: newsroom media gallery images videos stories update. "
        ) * 20
        result = score_page({
            "url": "https://www.esa.int/Science_Exploration/Space_Science/Juice",
            "title": "ESA - Juice",
            "text": noisy_text,
        })

        self.assertIn(result["triage"], {"accepted", "review_needed", "exploratory"})
        self.assertNotEqual(result["triage"], "rejected")

    def test_short_scientific_page_is_not_accepted(self):
        result = score_page({
            "url": "https://example.org/planet/mars",
            "title": "Mars",
            "text": "Mars is a planet.",
        })

        self.assertIn(result["triage"], {"review_needed", "rejected"})
        self.assertIn("short_text", result["labels"])

    def test_university_lab_page_is_accepted_or_review_needed(self):
        result = score_page({
            "url": "https://astro.example.edu/research/planetary-lab",
            "title": "Planetary Atmospheres Laboratory",
            "text": (
                "The university laboratory studies planetary atmospheres, Mars climate, telescope observations, "
                "orbital dynamics, spectroscopy, datasets, publications and student research projects. "
                "References include peer reviewed papers and NASA mission data."
            ),
        })

        self.assertIn(result["triage"], {"accepted", "review_needed"})
        self.assertIn("academic_source", result["labels"])

    def test_publication_abstract_page_is_accepted_or_review_needed(self):
        result = score_page({
            "url": "https://arxiv.org/abs/2401.01234",
            "title": "Abstract: Atmospheric escape from close-in exoplanets",
            "text": (
                "Abstract We present observations of exoplanet atmosphere escape using spectroscopy. "
                "The paper reports method, results, citations, references, DOI, and planetary science context."
            ),
        })

        self.assertIn(result["triage"], {"accepted", "review_needed"})
        self.assertIn("publication_page", result["labels"])

    def test_commercial_science_page_is_not_directly_accepted_without_strong_evidence(self):
        result = score_page({
            "url": "https://www.space-example.com/solar-system/mars-guide",
            "title": "Mars guide for beginners",
            "text": (
                "Mars is a planet in the solar system with atmosphere, moons, orbit and exploration history. "
                "This commercial science article is a readable overview with no references or data table."
            ),
        })

        self.assertIn(result["triage"], {"review_needed", "exploratory"})
        self.assertIn("commercial_or_unknown_source", result["labels"])

    def test_quality_context_threshold_can_keep_unknown_source_in_review(self):
        result = score_page(
            {
                "url": "https://www.space-example.com/solar-system/mars-data",
                "title": "Mars data overview",
                "html": "<table><tr><th>Mass</th><td>0.64</td></tr></table>"
                "<p>Mars planet atmosphere orbit radius diameter science reference.</p>",
            },
            quality_context={
                "source_mode": "generic_unknown",
                "topic_taxonomy": ["planetary_science"],
                "quality_gate": {"accepted_min_score": 90, "review_min_score": 30},
            },
        )

        self.assertEqual(result["triage"], "review_needed")
        self.assertIn("commercial_or_unknown_source", result["labels"])

    def test_entity_data_context_does_not_reject_metadata_only_records(self):
        result = score_page(
            {"url": "https://www.wikidata.org/wiki/Q111", "title": "火星", "text": ""},
            quality_context={
                "source_mode": "entity_data",
                "topic_taxonomy": ["astronomy", "planetary_science"],
                "quality_gate": {"accepted_min_score": 80, "review_min_score": 20},
            },
        )

        self.assertEqual(result["triage"], "review_needed")
        self.assertIn("entity_data_source", result["labels"])
        self.assertIn("topic_taxonomy_context", result["labels"])

    def test_rss_or_news_page_is_exploratory_not_rejected_when_it_has_body(self):
        result = score_page({
            "url": "https://science.example.org/rss/planetary-news",
            "title": "Planetary science RSS feed",
            "text": (
                "Recent planetary science news items summarize Mars mission updates, Jupiter observations, "
                "astronomy research releases and links to source articles."
            ),
        })

        self.assertEqual(result["triage"], "exploratory")
        self.assertIn("news_page", result["labels"])

    def test_policy_cookie_tag_and_navigation_pages_are_rejected(self):
        for candidate in (
            {"url": "https://example.org/privacy", "title": "Privacy Policy", "text": "Privacy and cookie policy."},
            {"url": "https://example.org/tags/mars", "title": "Mars tag", "text": "Tagged articles."},
            {
                "url": "https://example.org/site-map",
                "title": "Site navigation",
                "html": "<a href='/a'>A</a>" * 80 + "<p>Mars planet science links.</p>",
            },
        ):
            result = score_page(candidate)
            self.assertEqual(result["triage"], "rejected")

    def test_script_writes_report_in_temp_dir_and_uses_no_network_or_delete_tokens(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for token in ("urlopen", "requests.", "Remove-Item", "shutil.rmtree", "os.remove", ".unlink(", ".rmdir("):
            self.assertNotIn(token, source)

        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "candidates.json"
            report_path = root / "report.json"
            input_path.write_text(
                json.dumps([
                    {
                        "url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html",
                        "title": "Earth Fact Sheet",
                        "text": "Earth planet solar system mass radius diameter atmosphere orbit NASA facts.",
                    },
                    {"url": "https://example.org/privacy", "title": "Privacy", "text": "Privacy policy."},
                ]),
                encoding="utf-8",
            )

            exit_code = module.main([
                "--source",
                "nasa",
                "--input-json",
                str(input_path),
                "--report-json",
                str(report_path),
            ])

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["source"], "nasa")
        self.assertEqual(report["total"], 2)
        self.assertIn("items", report)


if __name__ == "__main__":
    unittest.main()

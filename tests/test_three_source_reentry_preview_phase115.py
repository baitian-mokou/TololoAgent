import tempfile
import unittest
from pathlib import Path

from scripts import three_source_reentry_preview_phase115 as phase115


class Phase115ControlledReentryPreviewTest(unittest.TestCase):
    def test_probe_limits(self):
        seeds = phase115.probe_seeds()
        self.assertLessEqual(sum(len(rows) for rows in seeds.values()), 9)
        for rows in seeds.values():
            self.assertLessEqual(len(rows), 3)

    def test_source_allowlist_and_bad_page_types(self):
        self.assertTrue(phase115.allowed_url("zh_wikipedia", "https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles=水星&format=json"))
        self.assertTrue(phase115.allowed_url("nasa", "https://images-api.nasa.gov/search?q=Juno&media_type=image&page_size=3"))
        self.assertTrue(phase115.allowed_url("nasa", "https://science.nasa.gov/wp-json/wp/v2/posts?per_page=3&search=Juno"))
        self.assertTrue(phase115.allowed_url("esa", "https://www.esa.int/Science_Exploration/Space_Science/Juice"))
        self.assertFalse(phase115.allowed_url("esa", "https://www.esa.int/Science_Exploration/Space_Science"))
        self.assertFalse(phase115.allowed_url("nasa", "https://science.nasa.gov/search/?search=Juno"))

    def test_quality_classifiers_reject_noise_and_meta_only_not_strong(self):
        self.assertEqual(phase115.classify_text("zh_wikipedia", "模板 infobox table 123"), "rejected")
        self.assertEqual(phase115.classify_text("esa", "<html>latest news index listing</html>"), "rejected")
        self.assertEqual(phase115.classify_text("nasa", "Juno is a NASA spacecraft studying Jupiter."), "conditional")
        self.assertEqual(phase115.classify_text("nasa", "Technicians install guidance, navigation and control components on NASA's Juno spacecraft."), "conditional")
        self.assertEqual(
            phase115.classify_text(
                "nasa",
                "The Juno spacecraft measures Jupiter's atmosphere and magnetic field during close flybys of the planet, returning instrument observations that describe the mission science context.",
            ),
            "accepted",
        )

    def test_report_flags_and_counts(self):
        report = phase115.build_preview(fetcher=lambda url: (599, "text/plain", ""))
        self.assertEqual(report["probe_limits"]["total_attempted"], 9)
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertEqual(set(report["source_counts"]), {"zh_wikipedia", "nasa", "esa"})

    def test_images_api_metadata_is_not_strong(self):
        payload = '{"collection":{"items":[{"data":[{"description":"The Juno spacecraft measures Jupiter and returns a long structured image description with mission context, instrument context, and science context for review."}]}]}}'
        record = phase115._record(
            "nasa",
            {
                "title": "Juno images metadata",
                "url": "https://images-api.nasa.gov/search?q=Juno&media_type=image&page_size=3",
                "method": "images_api_structured_description",
            },
            lambda url: (200, "application/json", payload),
        )
        self.assertEqual(record["quality_class"], "conditional")

    def test_output_guard_restricts_phase115_or_docs(self):
        self.assertFalse(phase115.output_allowed(Path(tempfile.gettempdir()) / "phase115.json"))
        self.assertFalse(phase115.output_allowed(phase115.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase115.output_allowed(phase115.ROOT / "evaluation" / "four_source_expansion" / "phase115" / "x.json"))
        self.assertTrue(phase115.output_allowed(phase115.ROOT / "docs" / "phase115.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

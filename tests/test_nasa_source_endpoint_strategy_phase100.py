import tempfile
import unittest
from pathlib import Path

from scripts import nasa_source_endpoint_strategy_phase100 as phase100


class Phase100NasaSourceEndpointStrategyTest(unittest.TestCase):
    def test_entry_limit_and_official_allowlist(self):
        entries = phase100.strategy_entries(limit_per_entry=5)

        self.assertLessEqual(len(entries), 3)
        self.assertLessEqual(sum(entry["limit"] for entry in entries), 15)
        for entry in entries:
            self.assertTrue(phase100.official_url(entry["url"]))

    def test_handles_auth_and_network_failures_without_crashing(self):
        report = phase100.judge_entry(
            {
                "strategy": "sample",
                "url": "https://api.nasa.gov/planetary/apod",
                "status": "http_403",
                "status_code": 403,
                "content_type": "application/json",
                "payload": "",
            },
            limit=5,
        )

        self.assertTrue(report["auth_required"])
        self.assertEqual(report["suitability_verdict"], "blocked_auth_required")

    def test_json_endpoint_with_body_fields_yields_preview_candidates(self):
        payload = [
            {
                "title": {"rendered": "Juno"},
                "link": "https://science.nasa.gov/mission/juno/",
                "excerpt": {"rendered": "Juno is a NASA mission studying Jupiter's atmosphere and magnetic field."},
                "content": {"rendered": "Juno is a NASA mission studying Jupiter, its atmosphere, magnetosphere, gravity, and origin."},
            }
        ]

        report = phase100.judge_entry(
            {
                "strategy": "science_wp_rest_posts",
                "url": "https://science.nasa.gov/wp-json/wp/v2/posts?per_page=5",
                "status": "http_200",
                "status_code": 200,
                "content_type": "application/json",
                "payload": payload,
            },
            limit=5,
        )

        self.assertEqual(report["sample_count"], 1)
        self.assertTrue(report["body_field_available"])
        self.assertEqual(report["suitability_verdict"], "usable_structured_body")
        self.assertEqual(report["preview_candidates"][0]["title"], "Juno")

    def test_output_guard_and_no_production_flags(self):
        report = phase100.build_report(entry_reports=[])

        self.assertFalse(phase100.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase100.output_allowed(phase100.ROOT / "evaluation" / "four_source_expansion" / "phase99" / "x.json"))
        self.assertTrue(phase100.output_allowed(phase100.ROOT / "evaluation" / "four_source_expansion" / "phase100" / "x.json"))
        self.assertTrue(phase100.output_allowed(phase100.ROOT / "docs" / "phase100.md", allow_docs=True))
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["formal_raw_write"])
        self.assertFalse(report["formal_default_triples_write"])
        self.assertTrue(report["active_source_unchanged"])


if __name__ == "__main__":
    unittest.main()

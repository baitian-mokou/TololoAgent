import tempfile
import unittest
from pathlib import Path

from scripts import three_source_extraction_repair_phase113 as phase113


class Phase113ExtractionRepairPreviewTest(unittest.TestCase):
    def test_noise_classifiers(self):
        self.assertEqual(phase113.classify_source_noise("zh_wikipedia", '{"narrative_excerpt": "表格 infobox"}'), "zh_json_template_table_noise")
        self.assertEqual(phase113.classify_source_noise("nasa", '["http://images-assets.nasa.gov/a.jpg"]'), "nasa_url_array_or_meta_thin")
        self.assertEqual(phase113.classify_source_noise("nasa", "<!doctype html><html><nav>search gallery menu</nav></html>"), "nasa_html_boilerplate")
        self.assertEqual(phase113.classify_source_noise("esa", "<html>latest news index listing</html>"), "esa_html_listing_or_index")

    def test_repair_only_when_meaningful_existing_text(self):
        repaired = phase113.repair_preview_record(
            {
                "source": "zh_wikipedia",
                "title_or_id": "太阳",
                "source_url_or_entity": "https://zh.wikipedia.org/wiki/太阳",
                "narrative": '{"narrative_excerpt": "太阳是太阳系中心的恒星，提供光和热。"}',
                "provenance": {"phase110_url_or_entity": "https://zh.wikipedia.org/wiki/太阳"},
            }
        )
        blocked = phase113.repair_preview_record(
            {
                "source": "nasa",
                "title_or_id": "Juno",
                "source_url_or_entity": "https://science.nasa.gov/x",
                "narrative": "<html><nav>search gallery menu footer</nav></html>",
                "provenance": {"phase110_url_or_entity": "https://science.nasa.gov/x"},
            }
        )

        self.assertEqual(repaired["repair_status"], "repaired_preview")
        self.assertTrue(repaired["narrative"])
        self.assertTrue(repaired["triples_preview"])
        self.assertEqual(blocked["repair_status"], "blocked")

    def test_report_counts_and_flags(self):
        report = phase113.build_repair_preview(
            phase112_rejected=phase113.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase112"
            / "rejected_queue_phase112.json",
            phase112_report=phase113.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase112"
            / "filtered_review_verdict_phase112.json",
            phase111_report=phase113.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase111"
            / "normalize_review_preview_phase111.json",
            phase110_report=phase113.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase110"
            / "controlled_deeper_crawl_preview_phase110.json",
        )

        self.assertEqual(report["source_counts"]["zh_wikipedia"]["total"], 3)
        self.assertEqual(report["source_counts"]["nasa"]["total"], 5)
        self.assertEqual(report["source_counts"]["esa"]["total"], 7)
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])

    def test_output_guard_restricts_phase113_or_docs(self):
        self.assertFalse(phase113.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase113.output_allowed(phase113.ROOT / "evaluation" / "four_source_expansion" / "phase112" / "x.json"))
        self.assertTrue(phase113.output_allowed(phase113.ROOT / "evaluation" / "four_source_expansion" / "phase113" / "x.json"))
        self.assertTrue(phase113.output_allowed(phase113.ROOT / "docs" / "phase113.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

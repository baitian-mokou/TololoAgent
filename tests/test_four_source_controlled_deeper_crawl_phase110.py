import tempfile
import unittest
from pathlib import Path

from scripts import four_source_controlled_deeper_crawl_phase110 as phase110


class Phase110ControlledDeeperCrawlPreviewTest(unittest.TestCase):
    def test_limits_stop_conditions_and_safety_flags(self):
        report = phase110.build_preview(
            phase109_gate=phase110.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase109"
            / "controlled_deeper_crawl_gate_phase109.json",
            phase104_report=phase110.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase104"
            / "verdict_report_phase104.json",
            fetcher=lambda url: {"status": "skipped_test_fetch", "status_code": 0, "text": ""},
            live_fetch=False,
        )

        self.assertLessEqual(report["total_attempted"], 80)
        self.assertEqual(report["limits"], {"zh_wikipedia": 20, "nasa": 10, "esa": 20, "wikidata": 30})
        self.assertIn("nasa", report["stop_reasons_by_source"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertFalse(report["formal_raw_write"])
        self.assertFalse(report["formal_default_triples_write"])
        self.assertEqual(report["active_source"], "zh_wikipedia")
        self.assertTrue(report["active_source_unchanged"])

    def test_quality_gates_classify_fixture_text(self):
        gate = phase110.load_gate(
            phase110.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase109"
            / "controlled_deeper_crawl_gate_phase109.json"
        )

        self.assertEqual(phase110.classify("zh_wikipedia", "太阳", "infobox table template " * 4, gate), "rejected")
        self.assertEqual(phase110.classify("esa", "ESA - Space Science", "latest news index listing missions", gate), "rejected")
        self.assertEqual(phase110.classify("nasa", "Juno", "navigation gallery search menu", gate), "rejected")
        self.assertEqual(phase110.classify("wikidata", "Q1", "claims source reference orbital period", gate), "accepted")

    def test_output_guard_restricts_phase110_or_docs(self):
        self.assertFalse(phase110.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase110.output_allowed(phase110.ROOT / "evaluation" / "four_source_expansion" / "phase109" / "x.json"))
        self.assertTrue(phase110.output_allowed(phase110.ROOT / "evaluation" / "four_source_expansion" / "phase110" / "x.json"))
        self.assertTrue(phase110.output_allowed(phase110.ROOT / "docs" / "phase110.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

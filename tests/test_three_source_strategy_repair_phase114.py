import tempfile
import unittest
from pathlib import Path

from scripts import three_source_strategy_repair_phase114 as phase114


class Phase114SourceStrategyRepairTest(unittest.TestCase):
    def test_probe_limits_are_enforced(self):
        candidates = phase114.strategy_candidates()
        self.assertLessEqual(sum(len(rows) for rows in candidates.values()), 9)
        for rows in candidates.values():
            self.assertLessEqual(len(rows), 3)

    def test_allowlist_and_bad_patterns(self):
        self.assertTrue(
            phase114.allowed_candidate(
                "zh_wikipedia",
                "https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles=太阳&format=json",
            )
        )
        self.assertTrue(phase114.allowed_candidate("nasa", "https://images-api.nasa.gov/search?q=Juno&media_type=image&page_size=3"))
        self.assertFalse(phase114.allowed_candidate("nasa", "https://science.nasa.gov/search/?search=Juno"))
        self.assertFalse(phase114.allowed_candidate("esa", "https://www.esa.int/Science_Exploration/Space_Science"))

    def test_report_counts_and_flags(self):
        report = phase114.build_strategy_preview(
            phase114.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase113"
            / "three_source_extraction_repair_preview_phase113.json",
            phase114.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase100"
            / "nasa_source_endpoint_strategy_preview_phase100.json",
        )

        self.assertEqual(report["probe_limits"]["total_attempted"], 9)
        self.assertEqual(report["source_counts"]["zh_wikipedia"]["attempted"], 3)
        self.assertEqual(report["source_counts"]["nasa"]["accepted_strategy_candidates"], 1)
        self.assertEqual(report["source_counts"]["esa"]["conditional_strategy_candidates"], 2)
        self.assertFalse(report["live_probe_used"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])

    def test_output_guard_restricts_phase114_or_docs(self):
        self.assertFalse(phase114.output_allowed(Path(tempfile.gettempdir()) / "phase114.json"))
        self.assertFalse(phase114.output_allowed(phase114.ROOT / "evaluation" / "four_source_expansion" / "phase113" / "x.json"))
        self.assertFalse(phase114.output_allowed(phase114.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase114.output_allowed(phase114.ROOT / "evaluation" / "four_source_expansion" / "phase114" / "x.json"))
        self.assertTrue(phase114.output_allowed(phase114.ROOT / "docs" / "phase114.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

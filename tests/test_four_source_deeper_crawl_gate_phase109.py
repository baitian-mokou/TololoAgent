import tempfile
import unittest
from pathlib import Path

from scripts import four_source_deeper_crawl_gate_phase109 as phase109


class Phase109ControlledDeeperCrawlGateTest(unittest.TestCase):
    def test_gate_config_limits_and_safety_flags(self):
        report = phase109.build_gate_design(
            phase108_report=phase109.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase108"
            / "source_repair_preview_phase108.json",
            phase107_closeout=phase109.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase107"
            / "final_closeout_phase107.json",
            phase106_report=phase109.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase106"
            / "item_verdict_report_phase106.json",
            phase105_handoff=phase109.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase105"
            / "review_handoff_phase105.json",
        )

        self.assertEqual(report["gate_readiness"], "ready_to_run_controlled_deeper_crawl_after_review")
        self.assertEqual(report["total_max_batch"], 80)
        self.assertEqual({k: v["max_batch"] for k, v in report["gate_config"]["sources"].items()}, {
            "zh_wikipedia": 20,
            "nasa": 10,
            "esa": 20,
            "wikidata": 30,
        })
        self.assertFalse(report["live_fetch_allowed_in_gate_design"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["formal_raw_write"])
        self.assertFalse(report["formal_default_triples_write"])

    def test_dry_run_evaluator_enforces_limits_and_required_gates(self):
        config = phase109.default_gate_config()
        result = phase109.evaluate_gate_config(config)

        self.assertTrue(result["schema_pass"])
        self.assertTrue(result["limit_pass"])
        self.assertTrue(result["safety_pass"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["preflight_allowed"])
        self.assertIn("search", config["sources"]["nasa"]["denylist"])
        self.assertIn("index", config["sources"]["esa"]["denylist"])
        self.assertIn("infobox", config["sources"]["zh_wikipedia"]["denylist"])
        self.assertIn("claim_filter", config["sources"]["wikidata"]["quality_gates"])

    def test_output_guard_restricts_phase109_or_docs(self):
        self.assertFalse(phase109.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(phase109.output_allowed(phase109.ROOT / "evaluation" / "four_source_expansion" / "phase108" / "x.json"))
        self.assertTrue(phase109.output_allowed(phase109.ROOT / "evaluation" / "four_source_expansion" / "phase109" / "x.json"))
        self.assertTrue(phase109.output_allowed(phase109.ROOT / "docs" / "phase109.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

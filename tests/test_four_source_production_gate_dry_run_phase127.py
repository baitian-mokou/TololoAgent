import tempfile
import unittest
from pathlib import Path

from scripts import four_source_production_gate_dry_run_phase127 as phase127


class Phase127FourSourceProductionGateDryRunTest(unittest.TestCase):
    def test_source_verdicts_and_blockers(self):
        report = phase127.build_report()

        self.assertEqual(report["source_verdicts"]["zh_wikipedia"], "manual_review_queue_candidate_not_production_ready")
        self.assertEqual(report["source_verdicts"]["esa"], "manual_review_pending_not_production_ready")
        self.assertEqual(report["source_verdicts"]["nasa"], "conditional_not_strong_blocked")
        self.assertEqual(report["source_verdicts"]["wikidata"], "thin_conditional_only_blocked")
        self.assertIn("manual_review_required", report["blockers"]["zh_wikipedia"])
        self.assertIn("manual_review_pending", report["blockers"]["esa"])
        self.assertIn("conditional_not_strong", report["blockers"]["nasa"])
        self.assertIn("thin_conditional_only", report["blockers"]["wikidata"])

    def test_dry_run_flags_are_all_false_for_writes_and_execution(self):
        report = phase127.build_report()

        self.assertTrue(report["dry_run_only"])
        for key in [
            "production_ready",
            "queue_allowed",
            "apply_allowed",
            "preflight_allowed",
            "ingest_allowed",
            "formal_raw_write",
            "formal_default_triples_write",
            "chroma_write",
            "neo4j_write",
        ]:
            self.assertFalse(report[key], key)
        self.assertEqual(report["active_source"], "zh_wikipedia")
        self.assertTrue(report["active_source_unchanged"])

    def test_output_guard_rejects_data_paths(self):
        self.assertTrue(phase127.output_allowed(phase127.REPORT_JSON))
        self.assertTrue(phase127.output_allowed(phase127.REPORT_MD, allow_docs=True))
        self.assertFalse(phase127.output_allowed(Path(tempfile.gettempdir()) / "phase127.json"))
        self.assertFalse(phase127.output_allowed(phase127.ROOT / "data" / "triples" / "x.json"))
        self.assertFalse(phase127.output_allowed(phase127.ROOT / "data" / "chroma_db" / "x.json"))


if __name__ == "__main__":
    unittest.main()

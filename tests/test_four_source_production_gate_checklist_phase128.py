import tempfile
import unittest
from pathlib import Path

from scripts import four_source_production_gate_checklist_phase128 as phase128


class Phase128ProductionGateChecklistTest(unittest.TestCase):
    def test_checklist_items_by_source(self):
        report = phase128.build_report()

        self.assertEqual(
            report["checklist"]["zh_wikipedia"],
            ["manual review queue approval", "stable evidence"],
        )
        self.assertEqual(
            report["checklist"]["esa"],
            ["manual review closure", "stronger acceptance evidence"],
        )
        self.assertEqual(
            report["checklist"]["nasa"],
            ["strong accepted sample evidence", "current conditional too weak"],
        )
        self.assertEqual(
            report["checklist"]["wikidata"],
            ["non-thin conditional evidence", "explicit blocked status"],
        )

    def test_all_execution_and_write_flags_are_false(self):
        report = phase128.build_report()

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

    def test_output_guard_allows_only_phase128_eval_and_docs(self):
        self.assertTrue(phase128.output_allowed(phase128.REPORT_JSON))
        self.assertTrue(phase128.output_allowed(phase128.REPORT_MD, allow_docs=True))
        self.assertFalse(phase128.output_allowed(Path(tempfile.gettempdir()) / "phase128.json"))
        self.assertFalse(phase128.output_allowed(phase128.ROOT / "data" / "triples" / "x.json"))


if __name__ == "__main__":
    unittest.main()

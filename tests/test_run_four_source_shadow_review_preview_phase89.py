import tempfile
import unittest
from pathlib import Path

from scripts import run_four_source_shadow_review_preview_phase89 as phase89


class Phase89ReviewPreviewTest(unittest.TestCase):
    def test_build_review_preview_samples_each_source_and_stays_non_production(self):
        report = phase89.build_preview(
            package_report=phase89.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase87"
            / "four_source_rebuilt_pending_shadow_package_phase87.json",
            gate_report=phase89.ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase88"
            / "four_source_rebuilt_readiness_gate_phase88.json",
            limit=2,
        )

        self.assertTrue(report["review_only"])
        self.assertFalse(report["production_ready"])
        self.assertEqual(report["review_status"], "pending")
        self.assertEqual(set(report["samples"]), set(phase89.REQUIRED_SOURCES))
        self.assertEqual(report["sample_counts"], {source: 2 for source in phase89.REQUIRED_SOURCES})
        self.assertEqual(report["nasa_repair_marker"], "title_or_excerpt")
        self.assertFalse(report["formal_default_triples_write"])
        self.assertFalse(report["chroma_write"])
        self.assertFalse(report["neo4j_write"])
        for rows in report["samples"].values():
            self.assertLessEqual(len(rows), 2)
            for row in rows:
                self.assertTrue(row["metadata"])
                self.assertTrue(row["provenance"])
                self.assertEqual(row["review_status"], "pending")

    def test_output_guard_rejects_outside_repo_and_non_phase89_eval(self):
        self.assertFalse(phase89.output_allowed(Path(tempfile.gettempdir()) / "docs" / "x.json"))
        self.assertFalse(
            phase89.output_allowed(
                phase89.ROOT / "evaluation" / "four_source_expansion" / "phase88" / "x.json"
            )
        )
        self.assertTrue(
            phase89.output_allowed(
                phase89.ROOT / "evaluation" / "four_source_expansion" / "phase89" / "x.json"
            )
        )
        self.assertTrue(phase89.output_allowed(phase89.ROOT / "docs" / "phase89.md", allow_docs=True))

    def test_cli_has_no_apply_option_and_rejects_bad_output(self):
        help_text = phase89.build_parser().format_help()
        self.assertNotIn("--apply", help_text)

        rc = phase89.main(["--out-json", str(Path(tempfile.gettempdir()) / "docs" / "x.json")])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from scripts.smoke_quality_review_workflow import run_smoke


class QualityReviewWorkflowSmokeTests(unittest.TestCase):
    def test_quality_review_workflow_smoke_passes_with_temp_final_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_report = root / "final_acceptance_report.json"
            output_report = root / "quality_review_workflow_smoke_report.json"
            final_report.write_text(json.dumps({"passed": True}, ensure_ascii=False), encoding="utf-8")

            report, exit_code = run_smoke(final_report_path=final_report, write_report=True, output_path=output_report)
            self.assertTrue(output_report.exists())

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["passed"])
        names = {item["name"]: item["passed"] for item in report["checks"]}
        for name in (
            "pending_does_not_write",
            "deferred_does_not_write",
            "rejected_does_not_write",
            "approved_metadata_only_dry_run_plan",
            "high_risk_value_change_blocked_by_default",
            "dry_run_writes_no_chroma",
            "dry_run_writes_no_neo4j",
            "high_risk_apply_attempt_writes_no_formal_value",
            "apply_attempt_writes_no_chroma",
            "apply_attempt_writes_no_neo4j",
            "active_source_still_zh_wikipedia",
            "run_all_gates_report_passed",
        ):
            self.assertTrue(names[name], name)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_quality_patch_decisions import validate_decisions


def write_payloads(root: Path):
    candidates = {
        "candidates": [
            {
                "patch_id": f"source_conflict_v4_{index:03d}",
                "action": "no_action_manual_review" if index != 2 else "add_measurement_kind",
            }
            for index in range(1, 9)
        ]
    }
    decisions = {
        "decisions": [
            {
                "patch_id": f"source_conflict_v4_{index:03d}",
                "subject": "测试",
                "relation": "HAS_RADIUS",
                "classification": "true_value_conflict",
                "recommended_decision": "defer_needs_external_source",
                "human_decision": "pending",
                "human_reason": "",
                "approved_action": None,
                "safe_to_apply": False,
                "reviewed_by": "",
                "reviewed_at": "",
            }
            for index in range(1, 9)
        ]
    }
    candidates_path = root / "candidates.json"
    decisions_path = root / "decisions.json"
    candidates_path.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
    decisions_path.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
    return candidates_path, decisions_path, decisions


class QualityPatchDecisionValidationTests(unittest.TestCase):
    def test_pending_template_passes_structure_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            candidates_path, decisions_path, _ = write_payloads(Path(tmpdir))

            report = validate_decisions(str(decisions_path), str(candidates_path))

            self.assertTrue(report["passed"])
            self.assertFalse(report["formal_data_written"])
            self.assertFalse(report["patches_applied"])

    def test_missing_patch_id_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            candidates_path, decisions_path, decisions = write_payloads(Path(tmpdir))
            decisions["decisions"] = decisions["decisions"][:-1]
            decisions_path.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")

            report = validate_decisions(str(decisions_path), str(candidates_path))

            self.assertFalse(report["passed"])
            self.assertEqual(report["errors"][0]["check"], "missing_patch_id")

    def test_approved_without_human_reason_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            candidates_path, decisions_path, decisions = write_payloads(Path(tmpdir))
            decisions["decisions"][0]["human_decision"] = "approved"
            decisions["decisions"][0]["safe_to_apply"] = True
            decisions["decisions"][0]["approved_action"] = "no_action_manual_review"
            decisions_path.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")

            report = validate_decisions(str(decisions_path), str(candidates_path))

            self.assertFalse(report["passed"])
            self.assertTrue(any(error["check"] == "approved_requires_human_reason" for error in report["errors"]))

    def test_approved_without_safe_to_apply_true_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            candidates_path, decisions_path, decisions = write_payloads(Path(tmpdir))
            decisions["decisions"][0]["human_decision"] = "approved"
            decisions["decisions"][0]["human_reason"] = "Reviewed by human."
            decisions["decisions"][0]["approved_action"] = "no_action_manual_review"
            decisions_path.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")

            report = validate_decisions(str(decisions_path), str(candidates_path))

            self.assertFalse(report["passed"])
            self.assertTrue(any(error["check"] == "approved_requires_safe_to_apply_true" for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()

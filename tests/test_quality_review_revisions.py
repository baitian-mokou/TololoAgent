import json
import tempfile
import unittest
from pathlib import Path

from scripts.apply_quality_patches import apply_quality_patch
from scripts.validate_quality_review_revisions import validate_quality_review_revisions


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_revision_fixture(root: Path):
    target = root / "data" / "triples" / "海王星_triples.json"
    write_json(target, [
        {"subject": "海王星", "relation": "HAS_MASS", "object": "1.0 kg"},
        {"subject": "海王星", "relation": "HAS_RADIUS", "object": "24,622 km"},
    ])
    queue = {
        "schema_version": "quality_review_queue_v1",
        "items": [
            {
                "review_id": "qr_value",
                "patch_id": "value_patch",
                "subject": "海王星",
                "relation": "HAS_MASS",
                "current_value": "1.0 kg",
                "proposed_value": "1.02413e26 kg",
                "issue_type": "true_value_conflict",
                "risk_level": "high",
                "change_type": "value_change",
                "action": "replace_value",
                "safe_to_apply": False,
                "target_file": str(target),
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["1.0 kg"]}},
            }
        ],
    }
    queue_path = root / "queue.json"
    decisions_path = root / "decisions.json"
    report_path = root / "apply_report.json"
    validation_path = root / "revision_validation.json"
    write_json(queue_path, queue)
    return target, queue_path, decisions_path, report_path, validation_path


def revision_decision(status="proposed", human_decision="pending", safe_to_apply=False):
    return {
        "schema_version": "quality_review_decisions_v1",
        "decisions": [
            {
                "review_id": "qr_value",
                "patch_id": "value_patch",
                "subject": "海王星",
                "relation": "HAS_MASS",
                "issue_type": "true_value_conflict",
                "risk_level": "high",
                "change_type": "value_change",
                "human_decision": human_decision,
                "human_reason": "approved_in_test" if human_decision == "approved" else "",
                "approved_action": "replace_value" if human_decision == "approved" else None,
                "safe_to_apply": safe_to_apply,
                "user_proposed_value": "1.02413e26",
                "user_proposed_unit": "kg",
                "user_revision_reason": "用权威来源修正质量数值。",
                "user_evidence_note": "测试证据备注。",
                "user_evidence_url": "https://example.invalid/neptune",
                "revision_status": status,
            }
        ],
    }


class QualityReviewRevisionTests(unittest.TestCase):
    def test_revision_decision_storage_does_not_write_formal_triples(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path, _ = write_revision_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_json(decisions_path, revision_decision(status="draft"))

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=False,
            )

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertEqual(report["revision_proposals"][0]["revision_status"], "draft")
            self.assertFalse(report["formal_data_written"])
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])

    def test_draft_revision_never_applies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path, _ = write_revision_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_json(decisions_path, revision_decision(status="draft", human_decision="approved", safe_to_apply=True))

            with self.assertRaises(RuntimeError):
                apply_quality_patch(
                    decisions_path=str(decisions_path),
                    candidates_path=str(queue_path),
                    report_path=str(report_path),
                    apply=True,
                    allow_value_change=True,
                    apply_value_changes=True,
                    backup_root=str(root / "backups"),
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertTrue(any("revision_status=validated" in error for error in report["errors"]))
            self.assertEqual(report["patches_applied"], 0)

    def test_proposed_revision_default_dry_run_shows_diff_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path, _ = write_revision_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_json(decisions_path, revision_decision(status="proposed"))

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=False,
            )

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            revision = report["revision_proposals"][0]
            self.assertEqual(revision["original_value"], "1.0 kg")
            self.assertEqual(revision["user_proposed_value"], "1.02413e26 kg")
            self.assertTrue(revision["requires_explicit_value_change"])
            self.assertEqual(report["applied_count"], 0)

    def test_proposed_revision_cannot_apply_without_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path, _ = write_revision_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_json(decisions_path, revision_decision(status="proposed", human_decision="approved", safe_to_apply=True))

            with self.assertRaises(RuntimeError):
                apply_quality_patch(
                    decisions_path=str(decisions_path),
                    candidates_path=str(queue_path),
                    report_path=str(report_path),
                    apply=True,
                    allow_value_change=True,
                    apply_value_changes=True,
                    backup_root=str(root / "backups"),
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertTrue(any("revision_status=validated" in error for error in report["errors"]))
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])

    def test_validated_revision_still_requires_allow_value_change_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path, _ = write_revision_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_json(decisions_path, revision_decision(status="validated", human_decision="approved", safe_to_apply=True))

            with self.assertRaises(RuntimeError):
                apply_quality_patch(
                    decisions_path=str(decisions_path),
                    candidates_path=str(queue_path),
                    report_path=str(report_path),
                    apply=True,
                    allow_value_change=False,
                    apply_value_changes=True,
                    backup_root=str(root / "backups"),
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertTrue(any("value_change requires --allow-value-change" in error for error in report["errors"]))
            self.assertEqual(report["patches_applied"], 0)

    def test_revision_validation_reports_safety_boundaries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, queue_path, decisions_path, _, validation_path = write_revision_fixture(root)
            write_json(decisions_path, revision_decision(status="proposed"))

            report = validate_quality_review_revisions(
                decisions_path=str(decisions_path),
                queue_path=str(queue_path),
                output_path=str(validation_path),
            )

            self.assertTrue(report["passed"])
            self.assertEqual(report["revision_status_counts"]["proposed"], 1)
            self.assertTrue(report["proposed_revision_default_apply_blocked"])
            self.assertFalse(report["formal_triples_written"])
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])

    def test_high_risk_proposed_revision_must_not_be_safe_to_apply(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, queue_path, decisions_path, _, validation_path = write_revision_fixture(root)
            write_json(decisions_path, revision_decision(status="proposed", safe_to_apply=True))

            report = validate_quality_review_revisions(
                decisions_path=str(decisions_path),
                queue_path=str(queue_path),
                output_path=str(validation_path),
            )

            self.assertFalse(report["passed"])
            self.assertTrue(any(error["check"] == "high_risk_revision_must_not_be_safe_to_apply_before_validation" for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()

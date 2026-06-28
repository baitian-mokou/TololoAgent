import json
import tempfile
import unittest
from pathlib import Path

from scripts.apply_quality_patches import apply_quality_patch


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def revision_fixture(root: Path):
    target = root / "data" / "triples" / "revision_triples.json"
    write_json(target, [
        {"subject": "月球", "relation": "ORBITS", "object": "Q2"},
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "bad_radius"},
        {"subject": "金星", "relation": "HAS_RADIUS", "object": "bad_venus_radius"},
    ])
    queue = {
        "schema_version": "quality_review_queue_v1",
        "items": [
            {
                "review_id": "qr_manual",
                "patch_id": "manual_patch",
                "subject": "月球",
                "relation": "ORBITS",
                "current_value": "Q2",
                "issue_type": "true_value_conflict",
                "risk_level": "high",
                "change_type": "manual_review",
                "action": "no_action_manual_review",
                "safe_to_apply": False,
                "target_file": str(target),
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["Q2"]}},
            },
            {
                "review_id": "qr_meta",
                "patch_id": "metadata_patch",
                "subject": "天王星",
                "relation": "HAS_RADIUS",
                "current_value": "bad_radius",
                "issue_type": "measurement_kind_mismatch",
                "risk_level": "low",
                "change_type": "metadata_only",
                "action": "add_measurement_kind",
                "safe_to_apply": True,
                "target_file": str(target),
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["bad_radius"]}},
                "proposed_metadata": {"measurement_kind": "unspecified_radius"},
            },
            {
                "review_id": "qr_proposed",
                "patch_id": "proposed_patch",
                "subject": "金星",
                "relation": "HAS_RADIUS",
                "current_value": "bad_venus_radius",
                "issue_type": "true_value_conflict",
                "risk_level": "high",
                "change_type": "manual_review",
                "action": "no_action_manual_review",
                "safe_to_apply": False,
                "target_file": str(target),
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["bad_venus_radius"]}},
            },
        ],
    }
    queue_path = root / "queue.json"
    decisions_path = root / "decisions.json"
    report_path = root / "apply_report.json"
    write_json(queue_path, queue)
    return target, queue_path, decisions_path, report_path


def revision_decision(patch_id, value, status="validated", safe=True, approved=True, unit=""):
    return {
        "review_id": f"qr_{patch_id}",
        "patch_id": patch_id,
        "subject": "月球",
        "relation": "ORBITS",
        "human_decision": "approved" if approved else "pending",
        "human_reason": "approved_in_test" if approved else "",
        "approved_action": "revision_value_change" if approved else None,
        "safe_to_apply": safe if approved else False,
        "user_proposed_value": value,
        "user_proposed_unit": unit,
        "user_revision_reason": "人工验证修正值。",
        "user_evidence_note": "测试证据。",
        "user_evidence_url": "https://example.invalid/source",
        "revision_status": status,
    }


def write_decisions(path: Path, decisions):
    write_json(path, {"schema_version": "quality_review_decisions_v1", "decisions": decisions})


class QualityReviewRevisionValueApplyTests(unittest.TestCase):
    def test_proposed_revision_does_not_enter_apply_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = revision_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_decisions(decisions_path, [
                revision_decision("proposed_patch", "6051.8", status="proposed", unit="km"),
            ])

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=False,
            )

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertEqual(report["apply_plan"], [])
            self.assertEqual(report["revision_proposals"][0]["revision_status"], "proposed")
            self.assertFalse(report["formal_data_written"])

    def test_validated_manual_review_revision_enters_dry_run_value_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = revision_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_decisions(decisions_path, [
                revision_decision("manual_patch", "地球"),
            ])

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=False,
            )

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertEqual(report["apply_plan"][0]["change_type"], "revision_value_change")
            self.assertEqual(report["apply_plan"][0]["original_change_type"], "manual_review")
            self.assertEqual(report["apply_plan"][0]["proposed_value"], "地球")

    def test_validated_metadata_only_revision_enters_value_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = revision_fixture(root)
            before = target.read_text(encoding="utf-8")
            decision = revision_decision("metadata_patch", "25362", unit="km")
            decision["subject"] = "天王星"
            decision["relation"] = "HAS_RADIUS"
            write_decisions(decisions_path, [decision])

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=False,
            )

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertEqual(report["apply_plan"][0]["change_type"], "revision_value_change")
            self.assertEqual(report["apply_plan"][0]["original_change_type"], "metadata_only")
            self.assertEqual(report["apply_plan"][0]["proposed_value"], "25362 km")

    def test_value_write_requires_allow_value_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = revision_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_decisions(decisions_path, [revision_decision("manual_patch", "地球")])

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
            self.assertTrue(any("--allow-value-change" in error for error in report["errors"]))
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])

    def test_value_write_requires_apply_value_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = revision_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_decisions(decisions_path, [revision_decision("manual_patch", "地球")])

            with self.assertRaises(RuntimeError):
                apply_quality_patch(
                    decisions_path=str(decisions_path),
                    candidates_path=str(queue_path),
                    report_path=str(report_path),
                    apply=True,
                    allow_value_change=True,
                    apply_value_changes=False,
                    backup_root=str(root / "backups"),
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertTrue(any("--apply-value-changes" in error for error in report["errors"]))

    def test_value_write_requires_safe_to_apply_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = revision_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_decisions(decisions_path, [revision_decision("manual_patch", "地球", safe=False)])

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
            self.assertTrue(any("safe_to_apply=true" in error for error in report["errors"]))

    def test_validated_revision_apply_creates_backup_and_rollback_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = revision_fixture(root)
            write_decisions(decisions_path, [revision_decision("manual_patch", "地球")])

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=True,
                allow_value_change=True,
                apply_value_changes=True,
                backup_root=str(root / "backups"),
            )
            records = json.loads(target.read_text(encoding="utf-8"))

            self.assertEqual(records[0]["object"], "地球")
            self.assertTrue(Path(report["backup_dir"]).exists())
            self.assertTrue(Path(report["rollback_manifest"]["path"]).exists())
            self.assertEqual(report["apply_plan"][0]["status"], "applied")
            self.assertTrue(report["formal_data_written"])
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])


if __name__ == "__main__":
    unittest.main()

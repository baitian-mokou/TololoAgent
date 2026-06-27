import json
import tempfile
import unittest
from pathlib import Path

from scripts.apply_quality_patches import apply_quality_patch


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_guard_fixture(root: Path):
    target = root / "data" / "triples" / "金星_triples.json"
    write_json(target, [
        {"subject": "金星", "relation": "HAS_RADIUS", "object": "1.0km"},
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "4km"},
    ])
    queue = {
        "schema_version": "quality_review_queue_v1",
        "items": [
            {
                "review_id": "qr_value",
                "patch_id": "value_patch",
                "subject": "金星",
                "relation": "HAS_RADIUS",
                "current_value": "1.0km",
                "proposed_value": "6051.8 km",
                "issue_type": "true_value_conflict",
                "risk_level": "high",
                "change_type": "value_change",
                "action": "replace_value",
                "safe_to_apply": True,
                "target_file": str(target),
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["1.0km"]}},
            },
            {
                "review_id": "qr_meta",
                "patch_id": "meta_patch",
                "subject": "天王星",
                "relation": "HAS_RADIUS",
                "current_value": "4km",
                "proposed_metadata": {"measurement_kind": "unspecified_radius"},
                "issue_type": "measurement_kind_mismatch",
                "risk_level": "low",
                "change_type": "metadata_only",
                "action": "add_measurement_kind",
                "safe_to_apply": True,
                "target_file": str(target),
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["4km"]}},
            },
        ],
    }
    queue_path = root / "queue.json"
    decisions_path = root / "decisions.json"
    report_path = root / "apply_report.json"
    write_json(queue_path, queue)
    return target, queue_path, decisions_path, report_path


class QualityReviewApplyGuardTests(unittest.TestCase):
    def test_pending_deferred_rejected_do_not_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = write_guard_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_json(decisions_path, {
                "decisions": [
                    {"patch_id": "value_patch", "human_decision": "pending", "safe_to_apply": False},
                    {"patch_id": "meta_patch", "human_decision": "deferred", "safe_to_apply": False},
                    {"patch_id": "missing_patch", "human_decision": "rejected", "safe_to_apply": False},
                ]
            })

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=True,
                backup_root=str(root / "backups"),
            )

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertEqual(report["applied_count"], 0)
            self.assertEqual(report["skipped_count"], 3)
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])

    def test_value_change_requires_allow_flag_for_apply(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = write_guard_fixture(root)
            before = target.read_text(encoding="utf-8")
            write_json(decisions_path, {
                "decisions": [
                    {
                        "patch_id": "value_patch",
                        "human_decision": "approved",
                        "human_reason": "approved_in_test",
                        "approved_action": "replace_value",
                        "safe_to_apply": True,
                    }
                ]
            })

            with self.assertRaises(RuntimeError):
                apply_quality_patch(
                    decisions_path=str(decisions_path),
                    candidates_path=str(queue_path),
                    report_path=str(report_path),
                    apply=True,
                    allow_value_change=False,
                    backup_root=str(root / "backups"),
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertTrue(any("value_change requires --allow-value-change" in error for error in report["errors"]))
            self.assertIsNone(report["backup_dir"])
            self.assertEqual(report["applied_count"], 0)
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])


if __name__ == "__main__":
    unittest.main()

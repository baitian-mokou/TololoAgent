import json
import tempfile
import unittest
from pathlib import Path

from scripts.apply_quality_patches import apply_quality_patch


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_metadata_fixture(root: Path):
    target = root / "data" / "triples" / "天王星_triples.json"
    write_json(target, [
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "4km"},
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "20km"},
    ])
    queue = {
        "schema_version": "quality_review_queue_v1",
        "items": [
            {
                "review_id": "qr_meta",
                "patch_id": "meta_patch",
                "subject": "天王星",
                "relation": "HAS_RADIUS",
                "current_value": ["4km", "20km"],
                "proposed_metadata": {"measurement_kind": "unspecified_radius", "quality_status": "approved_metadata_only"},
                "issue_type": "measurement_kind_mismatch",
                "risk_level": "low",
                "change_type": "metadata_only",
                "action": "add_measurement_kind",
                "safe_to_apply": True,
                "target_file": str(target),
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["4km", "20km"]}},
            }
        ],
    }
    decisions = {
        "schema_version": "quality_review_decisions_v1",
        "decisions": [
            {
                "review_id": "qr_meta",
                "patch_id": "meta_patch",
                "human_decision": "approved",
                "human_reason": "approved_in_test",
                "approved_action": "add_measurement_kind",
                "safe_to_apply": True,
            }
        ],
    }
    queue_path = root / "queue.json"
    decisions_path = root / "decisions.json"
    report_path = root / "apply_report.json"
    write_json(queue_path, queue)
    write_json(decisions_path, decisions)
    return target, queue_path, decisions_path, report_path


class QualityReviewApplyBackupTests(unittest.TestCase):
    def test_dry_run_does_not_write_or_create_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = write_metadata_fixture(root)
            before = target.read_text(encoding="utf-8")

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=False,
                backup_root=str(root / "backups"),
            )

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertEqual(len(report["apply_plan"]), 1)
            self.assertIsNone(report["backup_dir"])
            self.assertIsNone(report["rollback_manifest"])
            self.assertFalse((root / "backups").exists())

    def test_apply_metadata_only_creates_backup_and_rollback_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = write_metadata_fixture(root)
            before = json.loads(target.read_text(encoding="utf-8"))

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=True,
                backup_root=str(root / "backups"),
            )

            after = json.loads(target.read_text(encoding="utf-8"))
            manifest = report["rollback_manifest"]
            backup_path = Path(manifest["entries"][0]["backup_path"])
            backup_records = json.loads(backup_path.read_text(encoding="utf-8"))

            self.assertEqual(report["applied_count"], 1)
            self.assertEqual(report["patches_applied"], 1)
            self.assertTrue(Path(report["backup_dir"]).exists())
            self.assertTrue(Path(manifest["path"]).exists())
            self.assertEqual(manifest["entries"][0]["original_path"], str(target.resolve()))
            self.assertEqual(manifest["entries"][0]["patch_ids"], ["meta_patch"])
            self.assertEqual(backup_records, before)
            self.assertNotEqual(after, before)
            self.assertTrue(all(item.get("quality_patch_id") == "meta_patch" for item in after))
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])


if __name__ == "__main__":
    unittest.main()

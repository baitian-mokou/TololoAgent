import json
import tempfile
import unittest
from pathlib import Path

from scripts.apply_quality_patches import apply_quality_patch


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_dedup_fixture(root: Path):
    target = root / "data" / "triples" / "天王星_triples.json"
    write_json(target, [
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "4km"},
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "20km"},
        {"subject": "火星", "relation": "HAS_RADIUS", "object": "30km"},
    ])
    queue_path = root / "queue.json"
    decisions_path = root / "decisions.json"
    report_path = root / "apply_report.json"
    write_json(queue_path, {
        "schema_version": "quality_review_queue_v1",
        "items": [
            {
                "review_id": "qr_source_conflict_v4_002",
                "patch_id": "source_conflict_v4_002",
                "subject": "天王星",
                "relation": "HAS_RADIUS",
                "current_value": ["4km", "20km"],
                "proposed_value": None,
                "proposed_metadata": {"measurement_kind": "unspecified_radius"},
                "issue_type": "measurement_kind_mismatch",
                "risk_level": "low",
                "change_type": "metadata_only",
                "action": "add_measurement_kind",
                "safe_to_apply": True,
                "target_file": str(target),
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["4km", "20km"], "wikidata": ["25362 km"], "nasa": ["25362 km"]}},
            }
        ],
    })
    write_json(decisions_path, {
        "schema_version": "quality_review_decisions_v1",
        "decisions": [
            {
                "review_id": "qr_source_conflict_v4_002",
                "patch_id": "source_conflict_v4_002",
                "subject": "天王星",
                "relation": "HAS_RADIUS",
                "human_decision": "approved",
                "human_reason": "approve validated Uranus radius correction",
                "approved_action": "revision_value_change",
                "safe_to_apply": True,
                "reviewed_by": "test",
                "reviewed_at": "2026-06-28T13:20:00+00:00",
                "updated_at": "2026-06-28T13:20:00+00:00",
                "user_proposed_value": "25362",
                "user_proposed_unit": "km",
                "user_revision_reason": "wikidata/nasa both support 25362 km",
                "user_evidence_note": "wikidata: 25362 km; nasa: 25362 km",
                "user_evidence_url": "offline",
                "revision_status": "validated",
            }
        ],
    })
    return target, queue_path, decisions_path, report_path


class RevisionValueChangeDedupTests(unittest.TestCase):
    def test_duplicate_value_change_stays_blocked_without_explicit_dedup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = write_dedup_fixture(root)
            before = target.read_text(encoding="utf-8")

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
            self.assertTrue(report["apply_plan"][0]["would_create_duplicate"])
            self.assertFalse(report["apply_plan"][0]["dedup_enabled"])
            self.assertEqual(report["apply_plan"][0]["proposed_value"], "25362 km")
            self.assertEqual(report["patches_applied"], 0)
            self.assertIsNone(report["backup_dir"])
            self.assertIsNone(report["rollback_manifest"])
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])

    def test_duplicate_value_change_can_apply_with_explicit_dedup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path = write_dedup_fixture(root)

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=True,
                allow_value_change=True,
                apply_value_changes=True,
                deduplicate_value_change=True,
                backup_root=str(root / "backups"),
            )

            triples = json.loads(target.read_text(encoding="utf-8"))
            uranus_radius = [
                record for record in triples
                if record.get("subject") == "天王星" and record.get("relation") == "HAS_RADIUS"
            ]

            self.assertEqual(len(uranus_radius), 1)
            self.assertEqual(uranus_radius[0]["object"], "25362 km")
            self.assertEqual(triples[-1], {"subject": "火星", "relation": "HAS_RADIUS", "object": "30km"})
            self.assertEqual(report["apply_plan"][0]["deduplicated_records"][0]["removed_object"], "20km")
            self.assertTrue(Path(report["backup_dir"]).exists())
            self.assertTrue(Path(report["rollback_manifest"]["path"]).exists())
            self.assertEqual(report["rollback_manifest"]["entries"][0]["original_path"], str(target.resolve()))
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from scripts.apply_quality_patches import apply_quality_patch
from scripts.preflight_revision_value_changes import preflight_revision_value_changes


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_preflight_fixture(root: Path):
    target = root / "data" / "triples" / "preflight_triples.json"
    write_json(target, [
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "4km"},
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "20km"},
        {"subject": "月球", "relation": "ORBITS", "object": "太阳系内密度第二高"},
    ])
    queue = {
        "schema_version": "quality_review_queue_v1",
        "items": [
            {
                "review_id": "qr_radius",
                "patch_id": "radius_patch",
                "subject": "天王星",
                "relation": "HAS_RADIUS",
                "current_value": ["4km", "20km"],
                "risk_level": "low",
                "change_type": "metadata_only",
                "action": "add_measurement_kind",
                "target_file": str(target),
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["4km", "20km"]}},
            },
            {
                "review_id": "qr_orbits",
                "patch_id": "orbits_patch",
                "subject": "月球",
                "relation": "ORBITS",
                "current_value": "太阳系内密度第二高",
                "risk_level": "high",
                "change_type": "manual_review",
                "action": "no_action_manual_review",
                "target_file": str(target),
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["太阳系内密度第二高"]}},
            },
        ],
    }
    decisions = {
        "schema_version": "quality_review_decisions_v1",
        "decisions": [
            {
                "review_id": "qr_radius",
                "patch_id": "radius_patch",
                "subject": "天王星",
                "relation": "HAS_RADIUS",
                "human_decision": "pending",
                "safe_to_apply": False,
                "user_proposed_value": "25362",
                "user_proposed_unit": "km",
                "user_revision_reason": "人工修正半径。",
                "revision_status": "proposed",
            },
            {
                "review_id": "qr_orbits",
                "patch_id": "orbits_patch",
                "subject": "月球",
                "relation": "ORBITS",
                "human_decision": "pending",
                "safe_to_apply": False,
                "user_proposed_value": "地球",
                "user_revision_reason": "月球绕行地球。",
                "revision_status": "proposed",
            },
        ],
    }
    queue_path = root / "queue.json"
    decisions_path = root / "decisions.json"
    report_path = root / "preflight.json"
    apply_report_path = root / "apply_report.json"
    write_json(queue_path, queue)
    write_json(decisions_path, decisions)
    return target, queue_path, decisions_path, report_path, apply_report_path


class RevisionValueChangePreflightTests(unittest.TestCase):
    def test_multiple_old_values_to_same_new_value_marks_duplicate_risk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path, _ = write_preflight_fixture(root)
            before = target.read_text(encoding="utf-8")

            report = preflight_revision_value_changes(
                decisions_path=str(decisions_path),
                queue_path=str(queue_path),
                output_path=str(report_path),
            )
            by_patch = {item["patch_id"]: item for item in report["items"]}

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertTrue(by_patch["radius_patch"]["would_create_duplicate"])
            self.assertEqual(by_patch["radius_patch"]["duplicate_candidate_count"], 2)
            self.assertEqual(by_patch["radius_patch"]["duplicate_after_value"], "25362 km")
            self.assertIn(by_patch["radius_patch"]["recommended_next_action"], {"deduplicate_before_apply", "require_human_dedup_decision"})
            self.assertFalse(report["formal_triples_written"])

    def test_single_old_value_to_new_value_has_no_duplicate_risk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, report_path, _ = write_preflight_fixture(root)
            before = target.read_text(encoding="utf-8")

            report = preflight_revision_value_changes(
                decisions_path=str(decisions_path),
                queue_path=str(queue_path),
                output_path=str(report_path),
            )
            by_patch = {item["patch_id"]: item for item in report["items"]}

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertFalse(by_patch["orbits_patch"]["would_create_duplicate"])
            self.assertEqual(by_patch["orbits_patch"]["matched_record_count"], 1)
            self.assertEqual(by_patch["orbits_patch"]["recommended_next_action"], "no_duplicate_detected")
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])

    def test_proposed_revision_still_does_not_enter_apply_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target, queue_path, decisions_path, _, apply_report_path = write_preflight_fixture(root)
            before = target.read_text(encoding="utf-8")

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(apply_report_path),
                apply=False,
            )

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertEqual(report["apply_plan"], [])
            self.assertEqual(len(report["revision_proposals"]), 2)
            self.assertFalse(report["formal_data_written"])
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from scripts.apply_quality_patches import apply_quality_patch


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_review_fixture(root: Path):
    target = root / "data" / "triples" / "天王星_triples.json"
    write_json(target, [
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "4km"},
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "20km"},
        {"subject": "火星", "relation": "HAS_RADIUS", "object": "30km"},
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
                "proposed_value": None,
                "proposed_metadata": {"measurement_kind": "unspecified_radius", "quality_status": "approved_metadata_only"},
                "issue_type": "measurement_kind_mismatch",
                "risk_level": "low",
                "change_type": "metadata_only",
                "action": "add_measurement_kind",
                "safe_to_apply": True,
                "target_file": str(target),
                "target_record_hint": {"subject": "天王星", "relation": "HAS_RADIUS", "object": "4km"},
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["4km", "20km"]}},
            },
            {
                "review_id": "qr_value",
                "patch_id": "value_patch",
                "subject": "天王星",
                "relation": "HAS_RADIUS",
                "current_value": "4km",
                "proposed_value": "25362 km",
                "issue_type": "true_value_conflict",
                "risk_level": "high",
                "change_type": "value_change",
                "action": "replace_value",
                "safe_to_apply": False,
                "target_file": str(target),
                "source_evidence": {"values_by_source": {"zh_wikipedia": ["4km"], "wikidata": ["25362 km"]}},
            },
        ],
    }
    decisions = {
        "schema_version": "quality_review_decisions_v1",
        "decisions": [
            {
                "review_id": "qr_meta",
                "patch_id": "meta_patch",
                "human_decision": "pending",
                "human_reason": "",
                "approved_action": None,
                "safe_to_apply": False,
            },
            {
                "review_id": "qr_value",
                "patch_id": "value_patch",
                "human_decision": "pending",
                "human_reason": "",
                "approved_action": None,
                "safe_to_apply": False,
            },
        ],
    }
    queue_path = root / "queue.json"
    decisions_path = root / "decisions.json"
    report_path = root / "preview.json"
    write_json(queue_path, queue)
    write_json(decisions_path, decisions)
    return target, queue_path, decisions_path, report_path, decisions


class QualityReviewApplyTests(unittest.TestCase):
    def test_pending_rejected_and_deferred_are_not_applied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target, queue_path, decisions_path, report_path, decisions = write_review_fixture(Path(tmpdir))
            before = target.read_text(encoding="utf-8")
            decisions["decisions"][0]["human_decision"] = "rejected"
            decisions["decisions"][1]["human_decision"] = "deferred"
            write_json(decisions_path, decisions)

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=True,
            )

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertEqual(report["apply_plan"], [])
            self.assertEqual(report["patches_applied"], 0)
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])

    def test_approved_metadata_only_can_dry_run_without_writing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target, queue_path, decisions_path, report_path, decisions = write_review_fixture(Path(tmpdir))
            before = target.read_text(encoding="utf-8")
            decisions["decisions"][0].update({
                "human_decision": "approved",
                "human_reason": "approved_in_gui",
                "approved_action": "add_measurement_kind",
                "safe_to_apply": True,
            })
            write_json(decisions_path, decisions)

            report = apply_quality_patch(
                decisions_path=str(decisions_path),
                candidates_path=str(queue_path),
                report_path=str(report_path),
                apply=False,
            )

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertEqual(len(report["apply_plan"]), 1)
            self.assertEqual(report["apply_plan"][0]["change_type"], "metadata_only")
            self.assertFalse(report["formal_data_written"])
            self.assertFalse(report["chroma_written"])
            self.assertFalse(report["neo4j_written"])

    def test_high_risk_value_change_is_plan_only_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target, queue_path, decisions_path, report_path, decisions = write_review_fixture(Path(tmpdir))
            before = target.read_text(encoding="utf-8")
            decisions["decisions"][1].update({
                "human_decision": "approved",
                "human_reason": "approved_in_gui",
                "approved_action": "replace_value",
                "safe_to_apply": True,
            })
            write_json(decisions_path, decisions)

            with self.assertRaises(RuntimeError):
                apply_quality_patch(
                    decisions_path=str(decisions_path),
                    candidates_path=str(queue_path),
                    report_path=str(report_path),
                    apply=True,
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertEqual(report["apply_plan"][0]["status"], "blocked_value_change")
            self.assertEqual(report["patches_applied"], 0)
            self.assertFalse(report["formal_data_written"])


if __name__ == "__main__":
    unittest.main()

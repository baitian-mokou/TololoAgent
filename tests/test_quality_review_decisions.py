import json
import tempfile
import unittest
from pathlib import Path

import config
from scripts.validate_quality_patch_decisions import validate_decisions


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_review_payloads(root: Path):
    queue = {
        "schema_version": "quality_review_queue_v1",
        "items": [
            {
                "review_id": "qr_001",
                "patch_id": "p001",
                "subject": "天王星",
                "relation": "HAS_RADIUS",
                "issue_type": "measurement_kind_mismatch",
                "risk_level": "low",
                "change_type": "metadata_only",
                "action": "add_measurement_kind",
            }
        ],
    }
    decisions = {
        "schema_version": "quality_review_decisions_v1",
        "decisions": [
            {
                "review_id": "qr_001",
                "patch_id": "p001",
                "subject": "天王星",
                "relation": "HAS_RADIUS",
                "issue_type": "measurement_kind_mismatch",
                "risk_level": "low",
                "change_type": "metadata_only",
                "human_decision": "pending",
                "human_reason": "",
                "approved_action": None,
                "safe_to_apply": False,
            }
        ],
    }
    queue_path = root / "queue.json"
    decisions_path = root / "decisions.json"
    write_json(queue_path, queue)
    write_json(decisions_path, decisions)
    return queue_path, decisions_path, decisions


class QualityReviewDecisionTests(unittest.TestCase):
    def test_pending_review_decisions_validate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path, decisions_path, _ = write_review_payloads(Path(tmpdir))

            report = validate_decisions(str(decisions_path), str(queue_path))

        self.assertTrue(report["passed"])
        self.assertFalse(report["formal_data_written"])
        self.assertFalse(report["chroma_written"])
        self.assertFalse(report["neo4j_written"])

    def test_approved_review_decision_requires_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path, decisions_path, decisions = write_review_payloads(Path(tmpdir))
            decisions["decisions"][0].update({
                "human_decision": "approved",
                "safe_to_apply": True,
                "approved_action": "add_measurement_kind",
            })
            write_json(decisions_path, decisions)

            report = validate_decisions(str(decisions_path), str(queue_path))

        self.assertFalse(report["passed"])
        self.assertTrue(any(error["check"] == "approved_requires_human_reason" for error in report["errors"]))

    def test_approved_review_decision_with_gui_reason_validates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path, decisions_path, decisions = write_review_payloads(Path(tmpdir))
            decisions["decisions"][0].update({
                "human_decision": "approved",
                "human_reason": "approved_in_gui",
                "safe_to_apply": True,
                "approved_action": "add_measurement_kind",
            })
            write_json(decisions_path, decisions)

            report = validate_decisions(str(decisions_path), str(queue_path))

        self.assertTrue(report["passed"])

    def test_active_source_boundary_stays_zh_wikipedia(self):
        self.assertEqual(config.ACTIVE_SOURCE, "zh_wikipedia")
        self.assertEqual(config.SOURCE_REGISTRY.get("zh_wikipedia"), "active")
        for source in ("wikidata", "nasa", "esa"):
            self.assertEqual(config.SOURCE_REGISTRY.get(source), "disabled")


if __name__ == "__main__":
    unittest.main()

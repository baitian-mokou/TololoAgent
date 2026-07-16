import json
import tempfile
import unittest
from pathlib import Path

from src.gui.main_window import (
    QUALITY_REVIEW_WORKBENCH_BOTTOM_BUTTONS,
    QUALITY_REVIEW_WORKBENCH_GEOMETRY,
    QUALITY_REVIEW_WORKBENCH_MIN_SIZE,
    QUALITY_REVIEW_WORKBENCH_TITLE,
    QualityReviewTab,
)
from src.source_quality.review_labels import format_relation_label


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def make_review_tab(root: Path, decision, preflight_item):
    decisions_path = root / "decisions.json"
    preflight_path = root / "preflight.json"
    write_json(decisions_path, {"schema_version": "quality_review_decisions_v1", "decisions": [decision]})
    write_json(preflight_path, {"items": [preflight_item]})
    tab = QualityReviewTab.__new__(QualityReviewTab)
    tab.decisions_path = str(decisions_path)
    tab.preflight_path = str(preflight_path)
    tab._messages = []
    tab._log = tab._messages.append
    return tab, decisions_path


def moon_item():
    return {
        "review_id": "qr_source_conflict_v4_003",
        "patch_id": "source_conflict_v4_003",
        "subject": "月球",
        "relation": "ORBITS",
        "issue_type": "true_value_conflict",
        "risk_level": "high",
        "change_type": "manual_review",
        "action": "no_action_manual_review",
        "safe_to_apply": False,
    }


def moon_decision(status="validated"):
    return {
        **moon_item(),
        "human_decision": "pending",
        "human_reason": "",
        "approved_action": None,
        "safe_to_apply": False,
        "user_proposed_value": "地球",
        "user_proposed_unit": "",
        "user_revision_reason": "月球绕行地球。",
        "user_evidence_note": "测试证据。",
        "user_evidence_url": "",
        "revision_status": status,
    }


class QualityReviewGuiLayoutTests(unittest.TestCase):
    def test_workbench_window_geometry_is_configured(self):
        self.assertEqual(QUALITY_REVIEW_WORKBENCH_TITLE, "质量复查工作台")
        self.assertEqual(QUALITY_REVIEW_WORKBENCH_GEOMETRY, "1180x760")
        self.assertEqual(QUALITY_REVIEW_WORKBENCH_MIN_SIZE, (1000, 650))

    def test_workbench_bottom_buttons_include_primary_actions(self):
        expected = {
            "通过",
            "暂缓",
            "拒绝",
            "保存修正建议",
            "清除修正建议",
            "预演合并",
            "合并低风险标注",
            "导出复查报告",
            "刷新",
        }
        self.assertEqual(set(QUALITY_REVIEW_WORKBENCH_BOTTOM_BUTTONS), expected)

    def test_relation_label_still_uses_chinese_display_only(self):
        raw_relation = "HAS_RADIUS"
        self.assertEqual(format_relation_label(raw_relation), "HAS_RADIUS（半径）")
        self.assertEqual(raw_relation, "HAS_RADIUS")

    def test_approving_validated_revision_marks_value_change_safe_when_no_duplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tab, decisions_path = make_review_tab(
                Path(tmpdir),
                moon_decision(status="validated"),
                {"patch_id": "source_conflict_v4_003", "would_create_duplicate": False},
            )

            tab._set_decision_for_item(moon_item(), "approved")

            decision = json.loads(decisions_path.read_text(encoding="utf-8"))["decisions"][0]
            self.assertEqual(decision["revision_status"], "validated")
            self.assertEqual(decision["human_decision"], "approved")
            self.assertEqual(decision["approved_action"], "revision_value_change")
            self.assertTrue(decision["safe_to_apply"])

    def test_approving_duplicate_risk_revision_does_not_mark_safe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tab, decisions_path = make_review_tab(
                Path(tmpdir),
                moon_decision(status="validated"),
                {"patch_id": "source_conflict_v4_003", "would_create_duplicate": True},
            )

            tab._set_decision_for_item(moon_item(), "approved")

            decision = json.loads(decisions_path.read_text(encoding="utf-8"))["decisions"][0]
            self.assertEqual(decision["human_decision"], "pending")
            self.assertFalse(decision["safe_to_apply"])

    def test_saving_existing_validated_revision_does_not_downgrade_to_proposed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tab, decisions_path = make_review_tab(
                Path(tmpdir),
                moon_decision(status="validated"),
                {"patch_id": "source_conflict_v4_003", "would_create_duplicate": False},
            )

            tab._save_revision_for_item(moon_item(), "地球", "", "月球绕行地球。", "测试证据。", "")

            decision = json.loads(decisions_path.read_text(encoding="utf-8"))["decisions"][0]
            self.assertEqual(decision["revision_status"], "validated")


if __name__ == "__main__":
    unittest.main()

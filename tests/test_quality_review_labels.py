import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_quality_review_cards import generate_quality_review_cards
from src.source_quality.review_labels import (
    format_relation_label,
    format_status_explanation,
    recommended_action_for_review,
)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class QualityReviewLabelTests(unittest.TestCase):
    def test_known_relation_has_chinese_label(self):
        self.assertEqual(format_relation_label("HAS_RADIUS"), "HAS_RADIUS（半径）")

    def test_unknown_relation_is_left_raw(self):
        self.assertEqual(format_relation_label("HAS_UNKNOWN"), "HAS_UNKNOWN")

    def test_status_codes_are_translated_to_user_actions(self):
        self.assertIn("建议暂缓", format_status_explanation("defer_unresolved"))
        self.assertIn("抽取错误", format_status_explanation("mark_extraction_error"))
        item = {
            "issue_type": "true_value_conflict",
            "risk_level": "high",
            "source_evidence": {"external_review": {"recommendation": "mark_extraction_error"}},
        }
        self.assertEqual(recommended_action_for_review(item), "填写修正建议")

    def test_card_generation_keeps_raw_relation_and_adds_relation_label(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            queue_path = root / "quality_review_queue.json"
            markdown_path = root / "quality_review_cards.md"
            json_path = root / "quality_review_cards.json"
            write_json(queue_path, {
                "schema_version": "quality_review_queue_v1",
                "summary": {"item_count": 1},
                "items": [
                    {
                        "review_id": "qr_radius",
                        "patch_id": "source_conflict_v4_001",
                        "subject": "测试天体",
                        "relation": "HAS_RADIUS",
                        "current_value": "1 km",
                        "issue_type": "true_value_conflict",
                        "risk_level": "high",
                        "change_type": "manual_review",
                        "source_evidence": {
                            "values_by_source": {"zh_wikipedia": ["1 km"]},
                            "external_review": {
                                "recommendation": "defer_unresolved",
                                "comparison_result": "unresolved",
                                "confidence": 0.3,
                            },
                        },
                        "human_decision": "pending",
                        "safe_to_apply": False,
                    }
                ],
            })

            generate_quality_review_cards(str(queue_path), str(markdown_path), str(json_path))
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            cards = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(queue["items"][0]["relation"], "HAS_RADIUS")
        self.assertEqual(queue["items"][0]["relation_label"], "HAS_RADIUS（半径）")
        self.assertEqual(cards["cards"][0]["relation"], "HAS_RADIUS")
        self.assertEqual(cards["cards"][0]["relation_label"], "HAS_RADIUS（半径）")
        self.assertIn("HAS_RADIUS（半径）", markdown)
        self.assertNotIn("defer_unresolved", markdown)
        self.assertNotIn("unresolved", markdown)


if __name__ == "__main__":
    unittest.main()

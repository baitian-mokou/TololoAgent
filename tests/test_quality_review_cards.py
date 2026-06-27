import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_quality_review_cards import generate_quality_review_cards


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def make_item(index: int, decision: str):
    patch_id = f"source_conflict_v4_{index:03d}"
    high_risk = index != 2
    return {
        "review_id": f"qr_{patch_id}",
        "patch_id": patch_id,
        "subject": f"测试天体{index}",
        "relation": "HAS_RADIUS" if index % 2 == 0 else "HAS_MASS",
        "current_value": f"{index}km",
        "proposed_value": None,
        "proposed_metadata": {"measurement_kind": "unspecified_radius"} if index == 2 else {},
        "issue_type": "measurement_kind_mismatch" if index == 2 else "true_value_conflict",
        "risk_level": "low" if index == 2 else "high",
        "source_evidence": {
            "values_by_source": {"zh_wikipedia": [f"{index}km"], "wikidata": [f"{index + 1}km"]},
            "external_review": {
                "recommendation": "defer_unresolved",
                "comparison_result": "unresolved",
                "confidence": 0.5,
                "external_evidence": {"normalized_value": f"{index + 1}km", "source_url": "https://example.test"},
            } if high_risk else None,
        },
        "system_recommendation": "建议人工复核。",
        "human_decision": decision,
        "safe_to_apply": index == 2,
        "change_type": "metadata_only" if index == 2 else "manual_review",
        "action": "add_measurement_kind" if index == 2 else "no_action_manual_review",
    }


class QualityReviewCardTests(unittest.TestCase):
    def test_generate_cards_from_eight_item_queue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            decisions = ["pending", "approved", "rejected", "deferred", "pending", "pending", "pending", "pending"]
            queue_path = root / "quality_review_queue.json"
            markdown_path = root / "quality_review_cards.md"
            json_path = root / "quality_review_cards.json"
            triples_dir = root / "data" / "triples"
            write_json(queue_path, {
                "schema_version": "quality_review_queue_v1",
                "summary": {"item_count": 8},
                "items": [make_item(index, decisions[index - 1]) for index in range(1, 9)],
            })

            result = generate_quality_review_cards(str(queue_path), str(markdown_path), str(json_path))
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            cards = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(result["card_count"], 8)
        self.assertEqual(cards["card_count"], 8)
        self.assertTrue(cards["all_cards_have_chinese_summary"])
        self.assertFalse(cards["formal_triples_written"])
        self.assertFalse(cards["chroma_written"])
        self.assertFalse(cards["neo4j_written"])
        self.assertFalse(triples_dir.exists())
        self.assertIn("质量复查卡片", markdown)
        self.assertEqual([item["human_decision"] for item in queue["items"]], decisions)
        for item in queue["items"]:
            self.assertIn("user_facing_summary", item)
            self.assertIn("recommended_user_action", item)
            self.assertIn("risk_explanation", item)
            self.assertIn("evidence_summary", item)
            self.assertIn("merge_impact_summary", item)
            self.assertRegex(item["user_facing_summary"], r"[\u4e00-\u9fff]")


if __name__ == "__main__":
    unittest.main()

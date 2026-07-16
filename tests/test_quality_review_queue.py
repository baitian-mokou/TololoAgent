import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_quality_review_queue import build_quality_review_queue


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class QualityReviewQueueTests(unittest.TestCase):
    def test_queue_is_generated_from_conflict_and_external_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidates_path = root / "candidates.json"
            audit_path = root / "audit.json"
            external_path = root / "external.json"
            queue_path = root / "quality_review_queue.json"
            decisions_path = root / "quality_review_decisions.json"

            write_json(candidates_path, {
                "candidates": [
                    {
                        "patch_id": "source_conflict_v4_002",
                        "action": "add_measurement_kind",
                        "target_file": str(root / "data" / "triples" / "天王星_triples.json"),
                        "target_record_hint": {"subject": "天王星", "relation": "HAS_RADIUS", "object": "4km"},
                        "before": {"values_by_source": {"zh_wikipedia": ["4km", "20km"], "wikidata": ["25362 km"]}},
                        "after": {"proposal": "annotate candidate measurement_kind only"},
                        "confidence": 0.8,
                    }
                ]
            })
            write_json(audit_path, {
                "evidence_packets": [
                    {
                        "subject": "天王星",
                        "relation": "HAS_RADIUS",
                        "audit_classification": "measurement_kind_mismatch",
                        "reason": "Radius records mix measurement kinds.",
                        "evidence_by_source": {},
                    }
                ]
            })
            write_json(external_path, {
                "candidates": [
                    {
                        "patch_id": "external_review_source_conflict_v4_002",
                        "source_patch_id": "source_conflict_v4_002",
                        "subject": "天王星",
                        "relation": "HAS_RADIUS",
                        "action": "defer_unresolved",
                        "recommendation": "defer_unresolved",
                        "comparison_result": "unresolved",
                        "before": {"values_by_source": {"zh_wikipedia": ["1.0km"], "wikidata": ["6051.8 km"]}},
                        "after": {"proposal": "candidate only"},
                        "external_evidence": {"source_url": "https://example.test/evidence"},
                    }
                ]
            })

            result = build_quality_review_queue(
                candidates_path=str(candidates_path),
                audit_path=str(audit_path),
                external_candidates_path=str(external_path),
                queue_path=str(queue_path),
                decisions_path=str(decisions_path),
            )

            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            decisions = json.loads(decisions_path.read_text(encoding="utf-8"))

        self.assertEqual(result["item_count"], 1)
        self.assertEqual(queue["summary"]["metadata_only_count"], 1)
        self.assertEqual(queue["summary"]["pending_count"], 1)
        self.assertEqual(queue["summary"]["merged_external_review_count"], 1)
        self.assertEqual({item["patch_id"] for item in queue["items"]}, {"source_conflict_v4_002"})
        self.assertIn("external_review", queue["items"][0]["source_evidence"])
        self.assertEqual(queue["items"][0]["source_evidence"]["external_review"]["source_patch_id"], "source_conflict_v4_002")
        for item in queue["items"]:
            for key in (
                "review_id",
                "patch_id",
                "subject",
                "relation",
                "current_value",
                "issue_type",
                "risk_level",
                "source_evidence",
                "system_recommendation",
                "human_decision",
                "safe_to_apply",
                "created_at",
                "updated_at",
            ):
                self.assertIn(key, item)
            self.assertEqual(item["human_decision"], "pending")
        self.assertTrue(all(item["human_decision"] == "pending" for item in decisions["decisions"]))


if __name__ == "__main__":
    unittest.main()

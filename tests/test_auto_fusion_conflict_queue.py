import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_quality_review_queue import build_quality_review_queue
from scripts.collect_auto_fusion_conflicts import build_auto_fusion_conflict_candidates


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class AutoFusionConflictQueueTests(unittest.TestCase):
    def test_conflict_candidates_are_emitted_for_quality_review_queue(self):
        conflicts = [
            {
                "query": "火星半径是多少",
                "subject": "火星",
                "relation": "HAS_RADIUS",
                "authority_source": "nasa",
                "values": [
                    {"object": "3389.5 km", "sources": ["nasa"]},
                    {"object": "3396.2 km", "sources": ["wikidata"]},
                ],
                "selected_sources": ["nasa", "wikidata", "zh_wikipedia"],
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidates_path = root / "auto_fusion_conflicts.json"
            audit_path = root / "audit.json"
            queue_path = root / "quality_review_queue.json"
            decisions_path = root / "quality_review_decisions.json"

            payload = build_auto_fusion_conflict_candidates(conflicts, output_path=str(candidates_path))
            write_json(audit_path, {"evidence_packets": []})
            result = build_quality_review_queue(
                candidates_path=str(candidates_path),
                audit_path=str(audit_path),
                queue_path=str(queue_path),
                decisions_path=str(decisions_path),
            )
            queue = json.loads(queue_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["summary"]["candidate_count"], 1)
        self.assertEqual(payload["candidates"][0]["classification"], "true_value_conflict")
        self.assertEqual(payload["candidates"][0]["authority_source"], "nasa")
        self.assertEqual(result["item_count"], 1)
        self.assertEqual(queue["items"][0]["patch_id"], "auto_fusion_conflict_001")
        self.assertEqual(queue["items"][0]["issue_type"], "true_value_conflict")


if __name__ == "__main__":
    unittest.main()

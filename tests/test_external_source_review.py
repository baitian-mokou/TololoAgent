import json
import tempfile
import unittest
from pathlib import Path

from scripts import run_external_source_review as review


def write_inputs(root: Path):
    candidates = {
        "candidates": [
            candidate("source_conflict_v4_001", "天王星", "HAS_MASS", {"zh_wikipedia": ["0.0013 × 10 25 kg"], "wikidata": ["8.6810e25 kg"]}),
            candidate("source_conflict_v4_003", "月球", "ORBITS", {"zh_wikipedia": ["太阳系内密度第二高"], "wikidata": ["地球"]}),
            candidate("source_conflict_v4_004", "木卫二", "HAS_MASS", {"zh_wikipedia": ["0.000 013 × 10 22 kg"], "wikidata": ["4.7998e22 kg"]}),
            candidate("source_conflict_v4_005", "木卫四", "HAS_MASS", {"zh_wikipedia": ["0.000 137 × 10 23 kg"], "wikidata": ["1.0759e23 kg"]}),
            candidate("source_conflict_v4_007", "火卫一", "HAS_RADIUS", {"zh_wikipedia": ["11.1km"], "wikidata": ["11.2667 km"]}),
            candidate("source_conflict_v4_008", "金星", "HAS_RADIUS", {"zh_wikipedia": ["1.0km"], "wikidata": ["6051.8 km"]}),
        ]
    }
    audit = {
        "evidence_packets": [
            {"subject": item["target_record_hint"]["subject"], "relation": item["target_record_hint"]["relation"], "reason": "test packet"}
            for item in candidates["candidates"]
        ],
        "quality_patch_candidates": candidates["candidates"],
    }
    candidates_path = root / "source_conflict_resolution_candidates.json"
    audit_path = root / "source_conflict_audit_v4.json"
    candidates_path.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
    audit_path.write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")
    return candidates_path, audit_path


def candidate(patch_id, subject, relation, values_by_source):
    return {
        "patch_id": patch_id,
        "action": "no_action_manual_review",
        "target_record_hint": {
            "subject": subject,
            "relation": relation,
            "object": values_by_source.get("zh_wikipedia", [""])[0],
        },
        "before": {"values_by_source": values_by_source},
        "requires_human_approval": True,
    }


class ExternalSourceReviewTests(unittest.TestCase):
    def test_live_fetch_failure_outputs_unresolved_without_failing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidates_path, audit_path = write_inputs(root)

            def failing_fetcher(subject, relation):
                raise RuntimeError("network unavailable")

            report = review.run_review(
                candidates_path=str(candidates_path),
                audit_path=str(audit_path),
                report_json=str(root / "evaluation" / "external_source_review.json"),
                report_md=str(root / "docs" / "external_source_review.md"),
                orbits_md=str(root / "docs" / "orbits_ontology_review.md"),
                review_candidates_json=str(root / "data" / "quality_patches" / "external_source_review_candidates.json"),
                fetcher=failing_fetcher,
            )

            phobos_radius = next(item for item in report["records"] if item["patch_id"] == "source_conflict_v4_007")
            self.assertEqual(phobos_radius["comparison_result"], "unresolved")
            self.assertEqual(phobos_radius["recommendation"], "defer_unresolved")
            self.assertTrue(phobos_radius["fetch_errors"])
            self.assertFalse((root / "data" / "triples").exists())

    def test_orbits_conflict_is_marked_for_ontology_or_extraction_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidates_path, audit_path = write_inputs(root)

            report = review.run_review(
                candidates_path=str(candidates_path),
                audit_path=str(audit_path),
                report_json=str(root / "evaluation" / "external_source_review.json"),
                report_md=str(root / "docs" / "external_source_review.md"),
                orbits_md=str(root / "docs" / "orbits_ontology_review.md"),
                review_candidates_json=str(root / "data" / "quality_patches" / "external_source_review_candidates.json"),
                fetcher=lambda subject, relation: {"facts": [], "errors": []},
            )

            moon_orbits = next(item for item in report["records"] if item["patch_id"] == "source_conflict_v4_003")
            self.assertEqual(moon_orbits["comparison_result"], "ontology_rule_needed")
            self.assertIn(moon_orbits["recommendation"], {"mark_extraction_error", "add_ontology_constraint_candidate"})
            self.assertTrue(moon_orbits["requires_human_approval"])

    def test_external_review_candidates_require_human_approval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidates_path, audit_path = write_inputs(root)
            review_candidates_path = root / "data" / "quality_patches" / "external_source_review_candidates.json"

            review.run_review(
                candidates_path=str(candidates_path),
                audit_path=str(audit_path),
                report_json=str(root / "evaluation" / "external_source_review.json"),
                report_md=str(root / "docs" / "external_source_review.md"),
                orbits_md=str(root / "docs" / "orbits_ontology_review.md"),
                review_candidates_json=str(review_candidates_path),
                fetcher=lambda subject, relation: {"facts": [], "errors": []},
            )
            payload = json.loads(review_candidates_path.read_text(encoding="utf-8"))

            self.assertEqual(len(payload["candidates"]), 6)
            self.assertTrue(all(item["requires_human_approval"] is True for item in payload["candidates"]))
            self.assertTrue(all(item["safe_to_apply"] is False for item in payload["candidates"]))
            self.assertFalse(payload["boundary"]["formal_triples_written"])
            self.assertFalse(payload["boundary"]["patches_applied"])


if __name__ == "__main__":
    unittest.main()

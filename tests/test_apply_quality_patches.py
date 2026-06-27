import json
import tempfile
import unittest
from pathlib import Path

from scripts import apply_quality_patches as apply_mod


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def fixture_payloads(root: Path, approved=True):
    target = root / "data" / "triples" / "天王星_triples.json"
    records = [
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "4km"},
        {"subject": "天王星", "relation": "HAS_RADIUS", "object": "20km"},
        {"subject": "天王星", "relation": "HAS_MASS", "object": "0.0013 × 10 25 kg"},
        {"subject": "火星", "relation": "HAS_RADIUS", "object": "30km"},
    ]
    write_json(target, records)
    candidates = {
        "candidates": [
            {
                "patch_id": "source_conflict_v4_002",
                "action": "add_measurement_kind",
                "target_file": str(target),
                "before": {"values_by_source": {"zh_wikipedia": ["4km", "20km"]}},
            },
            {
                "patch_id": "source_conflict_v4_003",
                "action": "no_action_manual_review",
                "target_file": str(target),
                "before": {"values_by_source": {"zh_wikipedia": ["not-used"]}},
            },
        ]
    }
    decisions = {
        "decisions": [
            {
                "patch_id": "source_conflict_v4_002",
                "human_decision": "approved" if approved else "pending",
                "safe_to_apply": bool(approved),
                "approved_action": "add_measurement_kind" if approved else None,
            },
            {
                "patch_id": "source_conflict_v4_003",
                "human_decision": "approved",
                "safe_to_apply": True,
                "approved_action": "no_action_manual_review",
            },
        ]
    }
    candidates_path = root / "candidates.json"
    decisions_path = root / "decisions.json"
    report_path = root / "evaluation" / "quality_patch_apply_preview.json"
    write_json(candidates_path, candidates)
    write_json(decisions_path, decisions)
    return target, candidates_path, decisions_path, report_path


class ApplyQualityPatchesTests(unittest.TestCase):
    def test_dry_run_does_not_modify_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target, candidates, decisions, report = fixture_payloads(Path(tmpdir))
            before = target.read_text(encoding="utf-8")
            original_target = apply_mod.EXPECTED_TARGET_FILE
            apply_mod.EXPECTED_TARGET_FILE = str(target)
            try:
                result = apply_mod.apply_quality_patch(decisions_path=str(decisions), candidates_path=str(candidates), report_path=str(report), apply=False)
            finally:
                apply_mod.EXPECTED_TARGET_FILE = original_target


            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertFalse(result["formal_values_changed"])
            self.assertEqual(len(result["matched_records"]), 2)
            self.assertTrue(report.exists())

    def test_apply_only_updates_uranus_radius_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target, candidates, decisions, report = fixture_payloads(Path(tmpdir))
            original_target = apply_mod.EXPECTED_TARGET_FILE
            apply_mod.EXPECTED_TARGET_FILE = str(target)
            try:
                result = apply_mod.apply_quality_patch(decisions_path=str(decisions), candidates_path=str(candidates), report_path=str(report), apply=True)
            finally:
                apply_mod.EXPECTED_TARGET_FILE = original_target

            data = json.loads(target.read_text(encoding="utf-8"))

            self.assertEqual(result["patches_applied"], 1)
            self.assertFalse(result["formal_values_changed"])
            annotated = [item for item in data if item.get("quality_patch_id") == "source_conflict_v4_002"]
            self.assertEqual(len(annotated), 2)
            self.assertEqual({item["object"] for item in annotated}, {"4km", "20km"})
            for item in annotated:
                self.assertEqual(item["subject"], "天王星")
                self.assertEqual(item["relation"], "HAS_RADIUS")
                self.assertEqual(item["measurement_kind"], "unspecified_radius")
            other = [item for item in data if item["subject"] == "火星"][0]
            self.assertNotIn("quality_patch_id", other)

    def test_unapproved_patch_does_not_apply(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target, candidates, decisions, report = fixture_payloads(Path(tmpdir), approved=False)
            before = target.read_text(encoding="utf-8")
            original_target = apply_mod.EXPECTED_TARGET_FILE
            apply_mod.EXPECTED_TARGET_FILE = str(target)
            try:
                result = apply_mod.apply_quality_patch(decisions_path=str(decisions), candidates_path=str(candidates), report_path=str(report), apply=True)
            finally:
                apply_mod.EXPECTED_TARGET_FILE = original_target

            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertEqual(result["patches_applied"], 0)


if __name__ == "__main__":
    unittest.main()

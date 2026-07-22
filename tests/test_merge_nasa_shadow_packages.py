import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "merge_nasa_shadow_packages.py"


def load_script():
    spec = importlib.util.spec_from_file_location("merge_nasa_shadow_packages", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MergeNasaShadowPackagesTests(unittest.TestCase):
    def write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def make_package(self, root: Path, name: str, *, start: int, count: int, overlap_subject: str = "") -> Path:
        package = root / "evaluation" / "four_source_expansion" / name
        triples = []
        narratives = []
        for index in range(start, start + count):
            subject = overlap_subject if overlap_subject and index == start else f"NASA Item {index}"
            url = f"https://science.nasa.gov/mission/item-{index}/"
            triples.append(
                {
                    "subject": subject,
                    "predicate": "SOURCE_URL",
                    "object": url,
                    "source_url": url,
                    "source_title": subject,
                    "source_id": "nasa",
                    "validation_status": "accepted",
                    "evidence": url,
                    "confidence": 0.99,
                }
            )
            narratives.append(
                {
                    "page_title": subject,
                    "source_title": subject,
                    "source_url": url,
                    "source_id": "nasa",
                    "source_role": "primary",
                    "content": f"{subject} narrative.",
                }
            )
        self.write_json(package / "triples_preview.json", triples)
        self.write_json(package / "narratives_preview.json", narratives)
        self.write_json(
            package / "package_manifest.json",
            {"source_id": "nasa", "items": count, "triples": len(triples), "narratives": len(narratives)},
        )
        return package

    def make_approval(self, root: Path, decision: str, count: int) -> Path:
        approval = root / "evaluation" / "four_source_expansion" / "phase52_approval.json"
        self.write_json(
            approval,
            {
                "source_id": "nasa",
                "approval_decision": decision,
                "approved_item_count": count,
                "reviewer_notes": "",
            },
        )
        return approval

    def test_pending_approval_blocks_and_does_not_write(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            phase45 = self.make_package(root, "phase45", start=1, count=2)
            phase52 = self.make_package(root, "phase52", start=3, count=2)
            approval = self.make_approval(root, "pending", 0)

            report = module.build_merge_report(
                phase45_package_dir=phase45,
                phase52_package_dir=phase52,
                phase52_approval_path=approval,
                shadow_output_dir=root / "data" / "triples_shadow" / "nasa",
                execute=False,
            )

            self.assertFalse(report["allowed"])
            self.assertFalse(report["executed"])
            self.assertEqual(report["blocked_reason"], "approval_not_approved")
            self.assertEqual(report["expected_combined_counts"]["items"], 4)
            self.assertFalse((root / "data" / "triples_shadow" / "nasa").exists())

    def test_partial_approval_blocks(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            phase45 = self.make_package(root, "phase45", start=1, count=2)
            phase52 = self.make_package(root, "phase52", start=3, count=2)
            approval = self.make_approval(root, "approved_for_shadow_write", 1)

            report = module.build_merge_report(
                phase45_package_dir=phase45,
                phase52_package_dir=phase52,
                phase52_approval_path=approval,
                shadow_output_dir=root / "data" / "triples_shadow" / "nasa",
                execute=True,
            )

            self.assertFalse(report["allowed"])
            self.assertEqual(report["blocked_reason"], "approved_item_count_mismatch")
            self.assertFalse((root / "data" / "triples_shadow" / "nasa").exists())

    def test_overlap_blocks(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            phase45 = self.make_package(root, "phase45", start=1, count=2)
            phase52 = self.make_package(root, "phase52", start=3, count=2, overlap_subject="NASA Item 1")
            approval = self.make_approval(root, "approved_for_shadow_write", 2)

            report = module.build_merge_report(
                phase45_package_dir=phase45,
                phase52_package_dir=phase52,
                phase52_approval_path=approval,
                shadow_output_dir=root / "data" / "triples_shadow" / "nasa",
                execute=True,
            )

            self.assertFalse(report["allowed"])
            self.assertEqual(report["blocked_reason"], "package_overlap_detected")
            self.assertTrue(report["overlap_summary"]["subjects"])

    def test_approved_execute_merges_to_fixed_shadow_without_overwrite(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            phase45 = self.make_package(root, "phase45", start=1, count=2)
            phase52 = self.make_package(root, "phase52", start=3, count=2)
            approval = self.make_approval(root, "approved_for_shadow_write", 2)
            shadow_output = root / "data" / "triples_shadow" / "nasa"

            report = module.build_merge_report(
                phase45_package_dir=phase45,
                phase52_package_dir=phase52,
                phase52_approval_path=approval,
                shadow_output_dir=shadow_output,
                execute=True,
            )

            self.assertTrue(report["allowed"])
            self.assertTrue(report["executed"])
            self.assertEqual(report["combined_counts"], {"items": 4, "triples": 4, "narratives": 4})
            self.assertEqual(len(json.loads((shadow_output / "triples_preview.json").read_text())), 4)
            manifest = json.loads((shadow_output / "package_manifest.json").read_text())
            self.assertEqual(manifest["items"], 4)
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse(report["formal_default_triples_write"])
            self.assertFalse(report["chroma_write"])
            self.assertFalse(report["neo4j_write"])

    def test_rejects_non_fixed_shadow_output(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            phase45 = self.make_package(root, "phase45", start=1, count=2)
            phase52 = self.make_package(root, "phase52", start=3, count=2)
            approval = self.make_approval(root, "approved_for_shadow_write", 2)

            report = module.build_merge_report(
                phase45_package_dir=phase45,
                phase52_package_dir=phase52,
                phase52_approval_path=approval,
                shadow_output_dir=root / "data" / "triples" / "nasa_shadow",
                execute=True,
            )

            self.assertFalse(report["allowed"])
            self.assertEqual(report["blocked_reason"], "output_not_fixed_shadow_path")

    def test_phase61_pending_preflight_combined_counts(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            combined = self.make_package(root, "combined48", start=1, count=48)
            phase60 = self.make_package(root, "phase60", start=100, count=24)
            approval = self.make_approval(root, "pending", 0)

            report = module.build_merge_report(
                phase45_package_dir=combined,
                phase52_package_dir=phase60,
                phase52_approval_path=approval,
                shadow_output_dir=root / "data" / "triples_shadow" / "nasa",
                execute=False,
                report_phase="Phase 61",
            )

            self.assertEqual(report["phase"], "Phase 61")
            self.assertFalse(report["allowed"])
            self.assertEqual(report["blocked_reason"], "approval_not_approved")
            self.assertEqual(report["expected_combined_counts"], {"items": 72, "triples": 72, "narratives": 72})
            self.assertFalse((root / "data" / "triples_shadow" / "nasa").exists())

    def test_script_source_does_not_import_databases_or_mutate_active_source(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("ChromaStore", source)
        self.assertNotIn("Neo4jLoader", source)
        self.assertNotRegex(source, r"^ACTIVE_SOURCE\s*=")


if __name__ == "__main__":
    unittest.main()

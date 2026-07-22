import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_esa_shadow_package_phase69.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_esa_shadow_package_phase69", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildEsaShadowPackagePhase69Tests(unittest.TestCase):
    def write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def make_raw(self, path: Path, title="ESA - Rosetta", url="https://www.esa.int/science/rosetta"):
        self.write_json(
            path,
            {
                "title": title,
                "source_url": url,
                "url": url,
                "text": (f"{title}. ESA space science mission spacecraft planetary observations orbit telescope. " * 25),
                "quality_triage": "accepted",
                "quality_score": 80,
            },
        )

    def test_builds_pending_package_without_formal_writes(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "evaluation" / "four_source_expansion" / "raw.json"
            self.make_raw(raw)
            p67 = root / "p67.json"
            p68 = root / "p68.json"
            self.write_json(p67, {"candidate_statuses": [{"status": "accepted_for_package", "raw_path": str(raw), "url": "https://www.esa.int/science/rosetta"}]})
            self.write_json(p68, {"candidate_statuses": []})
            report = module.build_esa_package(
                phase67_json=p67,
                phase68_json=p68,
                out_dir=root / "evaluation" / "four_source_expansion" / "p69",
                approval_template=root / "evaluation" / "four_source_expansion" / "approval.json",
            )
            self.assertEqual(report["packaged_items"], 1)
            self.assertGreater(report["triples"], 0)
            self.assertGreater(report["narratives"], 0)
            self.assertEqual(report["approval_status"], "pending")
            self.assertFalse(report["formal_triples_write"])
            self.assertFalse((root / "data" / "triples").exists())

    def test_internal_title_subject_duplicate_excluded(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = root / "evaluation" / "four_source_expansion" / "a.json"
            b = root / "evaluation" / "four_source_expansion" / "b.json"
            self.make_raw(a, title="ESA - Duplicate", url="https://www.esa.int/science/a")
            self.make_raw(b, title="ESA - Duplicate", url="https://www.esa.int/science/b")
            p67 = root / "p67.json"
            p68 = root / "p68.json"
            self.write_json(
                p67,
                {"candidate_statuses": [{"status": "accepted_for_package", "raw_path": str(a)}, {"status": "accepted_for_package", "raw_path": str(b)}]},
            )
            self.write_json(p68, {"candidate_statuses": []})
            report = module.build_esa_package(
                phase67_json=p67,
                phase68_json=p68,
                out_dir=root / "evaluation" / "four_source_expansion" / "p69",
                approval_template=root / "evaluation" / "four_source_expansion" / "approval.json",
            )
            self.assertEqual(report["packaged_items"], 1)
            self.assertEqual(report["duplicate_skipped"], 1)

    def test_rejected_failed_overlap_excluded_and_output_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "evaluation" / "four_source_expansion" / "raw.json"
            self.make_raw(raw, title="ESA - Rejected Later", url="https://www.esa.int/science/rejected")
            p67 = root / "p67.json"
            p68 = root / "p68.json"
            self.write_json(p67, {"candidate_statuses": [{"status": "accepted_for_package", "raw_path": str(raw)}]})
            self.write_json(p68, {"candidate_statuses": [{"status": "rejected", "title": "ESA - Rejected Later", "url": "https://www.esa.int/science/rejected"}]})
            report = module.build_esa_package(
                phase67_json=p67,
                phase68_json=p68,
                out_dir=root / "evaluation" / "four_source_expansion" / "p69",
                approval_template=root / "evaluation" / "four_source_expansion" / "approval.json",
            )
            self.assertEqual(report["packaged_items"], 0)
            self.assertEqual(report["rejected_failed_skipped"], 1)
            self.assertTrue(module.output_allowed(ROOT / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(ROOT / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(root / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

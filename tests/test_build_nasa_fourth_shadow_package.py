import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_nasa_fourth_shadow_package.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_nasa_fourth_shadow_package", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildNasaFourthShadowPackageTests(unittest.TestCase):
    def write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def make_raw(self, path: Path, title="Fresh Object", url="https://science.nasa.gov/fresh/"):
        self.write_json(
            path,
            {
                "title": title,
                "source_url": url,
                "url": url,
                "text": (f"{title}. NASA science asteroid comet mission orbit discovery spacecraft observations. " * 20),
                "quality_triage": "accepted",
                "quality_score": 70,
            },
        )

    def test_builds_pending_package_without_formal_writes(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_path = root / "evaluation" / "four_source_expansion" / "p59" / "raw.json"
            self.make_raw(raw_path)
            phase59 = root / "evaluation" / "four_source_expansion" / "p59.json"
            self.write_json(phase59, {"candidate_statuses": [{"status": "accepted_for_package", "raw_preview_path": str(raw_path), "url": "https://science.nasa.gov/fresh/"}]})
            report = module.build_fourth_package(
                phase59_json=phase59,
                exclude_package_dirs=[],
                exclude_report_paths=[],
                out_dir=root / "evaluation" / "four_source_expansion" / "p60",
                approval_template=root / "evaluation" / "four_source_expansion" / "approval.json",
            )
            self.assertEqual(report["packaged_items"], 1)
            self.assertGreater(report["triples"], 0)
            self.assertEqual(report["approval_status"], "pending")
            self.assertFalse(report["formal_triples_write"])
            self.assertFalse((root / "data" / "triples").exists())

    def test_excludes_prior_overlap(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_path = root / "evaluation" / "four_source_expansion" / "p59" / "raw.json"
            self.make_raw(raw_path, title="Already There")
            phase59 = root / "evaluation" / "four_source_expansion" / "p59.json"
            prior = root / "evaluation" / "four_source_expansion" / "prior"
            self.write_json(phase59, {"candidate_statuses": [{"status": "accepted_for_package", "raw_preview_path": str(raw_path), "url": "https://science.nasa.gov/fresh/"}]})
            self.write_json(prior / "triples_preview.json", [{"subject": "Already There", "source_url": "https://science.nasa.gov/fresh/"}])
            self.write_json(prior / "narratives_preview.json", [])
            report = module.build_fourth_package(
                phase59_json=phase59,
                exclude_package_dirs=[prior],
                exclude_report_paths=[],
                out_dir=root / "evaluation" / "four_source_expansion" / "p60",
                approval_template=root / "evaluation" / "four_source_expansion" / "approval.json",
            )
            self.assertEqual(report["packaged_items"], 0)
            self.assertEqual(report["prior_excluded"], 1)

    def test_output_paths_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertTrue(module.output_allowed(root / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(root / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(root / "data" / "x.json"))


if __name__ == "__main__":
    unittest.main()

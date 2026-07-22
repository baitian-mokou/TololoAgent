import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_nasa_shadow_review_preview.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_nasa_shadow_review_preview", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunNasaShadowReviewPreviewTests(unittest.TestCase):
    def make_shadow_and_eval(self, root: Path) -> tuple[Path, Path]:
        shadow_dir = root / "data" / "triples_shadow" / "nasa"
        shadow_dir.mkdir(parents=True)
        triples = [{"subject": "Apophis", "predicate": "INSTANCE_OF", "object": "asteroid", "source_url": "https://science.nasa.gov/apophis/", "source_id": "nasa", "validation_status": "accepted", "evidence": "Apophis is an asteroid."}]
        narratives = [{"page_title": "Apophis", "content": "Apophis asteroid", "source_url": "https://science.nasa.gov/apophis/", "source_id": "nasa", "source_role": "primary"}]
        (shadow_dir / "triples_preview.json").write_text(json.dumps(triples), encoding="utf-8")
        (shadow_dir / "narratives_preview.json").write_text(json.dumps(narratives), encoding="utf-8")
        (shadow_dir / "package_manifest.json").write_text(json.dumps({"items": 1, "triples": 1, "narratives": 1}), encoding="utf-8")
        eval_path = root / "evaluation" / "four_source_expansion" / "eval.json"
        eval_path.parent.mkdir(parents=True)
        eval_path.write_text(json.dumps({"ready": True, "eval_cases": [{"case_id": "apophis", "query": "Apophis", "oracle": {"subject": "Apophis"}}]}), encoding="utf-8")
        return shadow_dir, eval_path

    def test_missing_review_flag_blocks(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shadow, eval_path = self.make_shadow_and_eval(root)
            out_json = root / "evaluation" / "four_source_expansion" / "out.json"
            code = module.main(["--shadow-dir", str(shadow), "--eval-report-json", str(eval_path), "--out-json", str(out_json)])
            self.assertEqual(code, 2)
            report = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(report["blocked_reason"], "review_only_flag_required")

    def test_review_flag_returns_mapping(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shadow, eval_path = self.make_shadow_and_eval(root)
            out_json = root / "evaluation" / "four_source_expansion" / "out.json"
            code = module.main(["--review-only", "--shadow-dir", str(shadow), "--eval-report-json", str(eval_path), "--out-json", str(out_json)])
            self.assertEqual(code, 0)
            report = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertTrue(report["ready"])
            self.assertEqual(report["mapping_count"], 1)
            self.assertFalse((root / "data" / "triples").exists())

    def test_output_paths_restricted(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertTrue(module.output_allowed(root / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(root / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(root / "data" / "x.json"))


if __name__ == "__main__":
    unittest.main()

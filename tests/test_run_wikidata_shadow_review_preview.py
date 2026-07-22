import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_wikidata_shadow_review_preview.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_wikidata_shadow_review_preview", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunWikidataShadowReviewPreviewTests(unittest.TestCase):
    def write_eval(self, path: Path, *, ready=True, cases=10):
        path.parent.mkdir(parents=True, exist_ok=True)
        case_results = [
            {
                "query": f"Wikidata query {i}",
                "passed": True,
                "hit_count": 1,
                "top_results": [{"kind": "triple", "subject": "火星", "predicate": "ORBITS", "object": "太阳", "qid": "Q111", "source_url": "https://www.wikidata.org/wiki/Q111", "evidence": "wikidata adapter record"}],
            }
            for i in range(cases)
        ]
        path.write_text(json.dumps({"ready": ready, "eval": {"case_results": case_results}}), encoding="utf-8")

    def test_missing_review_flag_blocks(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            eval_path = root / "evaluation" / "four_source_expansion" / "eval.json"
            self.write_eval(eval_path)
            report = module.build_review_report(eval_report_path=eval_path, shadow_dir=root / "data" / "triples_shadow" / "wikidata", review_only=False)
            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "review_only_flag_required")

    def test_review_flag_returns_ten_mappings(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            eval_path = root / "evaluation" / "four_source_expansion" / "eval.json"
            self.write_eval(eval_path, cases=10)
            report = module.build_review_report(eval_report_path=eval_path, shadow_dir=root / "data" / "triples_shadow" / "wikidata", review_only=True)
            self.assertTrue(report["ready"])
            self.assertEqual(report["mapping_count"], 10)
            self.assertEqual(report["adapter_mappings"][0]["source_id"], "wikidata")
            self.assertEqual(report["adapter_mappings"][0]["qid"], "Q111")
            self.assertFalse((root / "data" / "triples").exists())

    def test_ready_false_blocks(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            eval_path = root / "evaluation" / "four_source_expansion" / "eval.json"
            self.write_eval(eval_path, ready=False)
            report = module.build_review_report(eval_report_path=eval_path, shadow_dir=root / "data" / "triples_shadow" / "wikidata", review_only=True)
            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "phase78_eval_not_ready")

    def test_output_paths_restricted(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp:
            outside = Path(temp)
            self.assertTrue(module.output_allowed(ROOT / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(ROOT / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(ROOT / "data" / "x.json"))
            self.assertFalse(module.output_allowed(outside / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

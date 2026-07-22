import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preview_esa_raw_batch_phase68.py"


def load_module():
    spec = importlib.util.spec_from_file_location("preview_esa_raw_batch_phase68", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreviewEsaRawBatchPhase68Tests(unittest.TestCase):
    def write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def fake_fetcher(self, url: str, timeout: int):
        return {
            "source_url": url,
            "title": url.rsplit("/", 1)[-1],
            "text": "ESA space science mission spacecraft orbit planetary observations " * 30,
        }

    def test_max_batch_and_evaluation_only(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            phase67 = root / "phase67.json"
            self.write_json(
                phase67,
                {"candidate_statuses": [{"status": "review_needed", "url": f"https://www.esa.int/Science_Exploration/Space_Science/{i}"} for i in range(20)]},
            )
            out_dir = root / "evaluation" / "four_source_expansion" / "phase68"
            report = module.preview_batch(phase67_json=phase67, out_dir=out_dir, limit=99, fetcher=self.fake_fetcher)
            self.assertEqual(report["selected"], 16)
            self.assertEqual(report["attempted"], 16)
            self.assertFalse((root / "data").exists())
            self.assertFalse(report["formal_raw_write"])
            self.assertFalse(report["chroma_write"])

    def test_output_restricted_to_repo_docs_or_evaluation(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            outside = Path(temp)
            self.assertTrue(module.output_allowed(ROOT / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(ROOT / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(outside / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertFalse(module.output_allowed(outside / "docs" / "x.md", allow_docs=True))

    def test_only_review_needed_and_esa_urls_are_previewed(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            phase67 = root / "phase67.json"
            self.write_json(
                phase67,
                {
                    "candidate_statuses": [
                        {"status": "accepted_for_package", "url": "https://www.esa.int/accepted"},
                        {"status": "review_needed", "url": "https://www.esa.int/review"},
                        {"status": "review_needed", "url": "https://example.com/nope"},
                    ]
                },
            )
            report = module.preview_batch(phase67_json=phase67, out_dir=root / "evaluation" / "four_source_expansion" / "phase68", fetcher=self.fake_fetcher)
            self.assertEqual(report["selected"], 1)
            self.assertEqual(report["invalid_excluded"], 1)
            self.assertEqual(report["candidate_statuses"][0]["url"], "https://www.esa.int/review")


if __name__ == "__main__":
    unittest.main()

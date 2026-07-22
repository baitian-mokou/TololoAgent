import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preview_nasa_raw_batch_phase59.py"


def load_module():
    spec = importlib.util.spec_from_file_location("preview_nasa_raw_batch_phase59", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreviewNasaRawBatchPhase59Tests(unittest.TestCase):
    def write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def fake_fetcher(self, url: str, timeout: int):
        body = "<html><head><title>NASA Good</title></head><body>" + (
            "NASA science mission asteroid comet planet orbit discovery spacecraft research observations. " * 30
        ) + "</body></html>"
        return {"url": url, "content_type": "text/html", "body": body}

    def test_batch_limit_and_evaluation_output_only(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            phase58 = root / "evaluation" / "four_source_expansion" / "p58.json"
            self.write_json(phase58, {"review_needed_candidates": [{"url": f"science.nasa.gov/{i}"} for i in range(35)]})
            report = module.preview_batch(phase58_json=phase58, out_dir=root / "evaluation" / "four_source_expansion" / "p59", limit=30, fetcher=self.fake_fetcher)
            self.assertEqual(report["attempted"], 30)
            self.assertFalse((root / "data" / "raw_json").exists())
            self.assertFalse(report["chroma_write"])

    def test_prior_report_exclusion(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            phase58 = root / "evaluation" / "four_source_expansion" / "p58.json"
            prior = root / "evaluation" / "four_source_expansion" / "prior.json"
            self.write_json(phase58, {"review_needed_candidates": [{"url": "science.nasa.gov/a"}, {"url": "science.nasa.gov/b"}]})
            self.write_json(prior, {"candidate_statuses": [{"status": "rejected", "url": "https://science.nasa.gov/a"}]})
            report = module.preview_batch(phase58_json=phase58, out_dir=root / "evaluation" / "four_source_expansion" / "p59", limit=30, exclude_report_paths=[prior], fetcher=self.fake_fetcher)
            self.assertEqual(report["prior_excluded"], 1)
            self.assertEqual(report["attempted"], 1)

    def test_output_paths_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertTrue(module.output_allowed(root / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(root / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(root / "data" / "x.json"))


if __name__ == "__main__":
    unittest.main()

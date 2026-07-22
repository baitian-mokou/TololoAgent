import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "assess_esa_controlled_preview.py"


def load_module():
    spec = importlib.util.spec_from_file_location("assess_esa_controlled_preview", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AssessEsaControlledPreviewTests(unittest.TestCase):
    def write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_max_batch_and_evaluation_only(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frontier = root / "evaluation" / "source_frontiers" / "esa_frontier.json"
            raw_root = root / "data" / "raw_json" / "esa"
            self.write_json(frontier, {"accepted": [{"url": f"https://www.esa.int/Science_Exploration/Space_Science/{i}"} for i in range(40)]})
            self.write_json(raw_root / "0.json", {"source_url": "https://www.esa.int/Science_Exploration/Space_Science/0", "title": "ESA 0", "text": "ESA space science mission planetary spacecraft orbit observations " * 20})
            report = module.assess_esa(frontier_json=frontier, raw_roots=[raw_root], limit=30)
            self.assertEqual(report["selected"], 30)
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse(report["chroma_write"])

    def test_source_remains_disabled_and_output_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            outside = Path(temp)
            self.assertTrue(module.output_allowed(ROOT / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(ROOT / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(outside / "docs" / "x.md", allow_docs=True))
            self.assertEqual(module.SOURCE_REGISTRY.get("esa"), "disabled")


if __name__ == "__main__":
    unittest.main()

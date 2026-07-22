import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_nasa_frontier_candidates.py"


def load_module():
    spec = importlib.util.spec_from_file_location("refresh_nasa_frontier_candidates", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RefreshNasaFrontierCandidatesTests(unittest.TestCase):
    def write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_excludes_prior_packages_and_rejections(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frontier = root / "evaluation" / "source_frontiers" / "nasa_frontier.json"
            raw_root = root / "data" / "raw_json" / "nasa"
            phase45 = root / "evaluation" / "four_source_expansion" / "phase45"
            phase57_report = root / "evaluation" / "four_source_expansion" / "phase57.json"
            self.write_json(
                frontier,
                {
                    "accepted": [
                        {"url": "https://science.nasa.gov/a/"},
                        {"url": "https://science.nasa.gov/b/"},
                        {"url": "https://science.nasa.gov/c/"},
                    ]
                },
            )
            self.write_json(phase45 / "triples_preview.json", [{"subject": "A", "source_url": "https://science.nasa.gov/a/"}])
            self.write_json(phase45 / "narratives_preview.json", [])
            self.write_json(phase57_report, {"candidate_statuses": [{"status": "rejected", "url": "https://science.nasa.gov/b/"}]})
            self.write_json(
                raw_root / "c.json",
                {
                    "source_url": "https://science.nasa.gov/c/",
                    "title": "C",
                    "text": "NASA science mission asteroid comet planet orbit discovery spacecraft research observations " * 20,
                },
            )

            report = module.refresh_frontier(
                frontier_json=frontier,
                raw_root=raw_root,
                exclude_package_dirs=[phase45],
                exclude_report_paths=[phase57_report],
                target_count=50,
            )

            self.assertEqual(report["accepted_for_next_preview"], 1)
            self.assertEqual(report["prior_excluded"], 2)
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse(report["chroma_write"])
            self.assertFalse(report["neo4j_write"])

    def test_output_paths_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertTrue(module.output_allowed(root / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(root / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(root / "data" / "x.json"))


if __name__ == "__main__":
    unittest.main()

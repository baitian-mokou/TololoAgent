import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "report_nasa_shadow_source_readiness.py"


def load_module():
    spec = importlib.util.spec_from_file_location("report_nasa_shadow_source_readiness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NasaShadowSourceReadinessTests(unittest.TestCase):
    def make_shadow_dir(self, root: Path, *, items: int = 1, triples_count: int = 2, narratives_count: int = 2) -> Path:
        shadow_dir = root / "data" / "triples_shadow" / "nasa"
        shadow_dir.mkdir(parents=True)
        triples = [
            {
                "subject": "Apophis",
                "predicate": "INSTANCE_OF",
                "object": "asteroid",
                "evidence": "Apophis is an asteroid.",
                "confidence": 0.82,
                "validation_status": "accepted",
                "source_id": "nasa",
                "source_url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "source_title": "Apophis - NASA Science",
            },
            {
                "subject": "Apophis",
                "predicate": "SOURCE_URL",
                "object": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "evidence": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "confidence": 0.99,
                "validation_status": "accepted",
                "source_id": "nasa",
                "source_url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "source_title": "Apophis - NASA Science",
            },
        ][:triples_count]
        narratives = [
            {
                "page_title": "Apophis - NASA Science",
                "content": "Apophis is a near-Earth asteroid observed by NASA.",
                "source_id": "nasa",
                "source": "nasa",
                "source_role": "primary",
                "source_url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "schema_version": "nasa_shadow_ready_v1",
            },
            {
                "page_title": "Apophis - NASA Science",
                "content": "NASA tracks Apophis as part of planetary defense.",
                "source_id": "nasa",
                "source": "nasa",
                "source_role": "primary",
                "source_url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "schema_version": "nasa_shadow_ready_v1",
            },
        ][:narratives_count]
        manifest = {"source_id": "nasa", "items": items, "triples": triples_count, "narratives": narratives_count, "formal_write": False}
        (shadow_dir / "triples_preview.json").write_text(json.dumps(triples), encoding="utf-8")
        (shadow_dir / "narratives_preview.json").write_text(json.dumps(narratives), encoding="utf-8")
        (shadow_dir / "package_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return shadow_dir

    def test_missing_shadow_files_are_blocked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow_dir = root / "data" / "triples_shadow" / "nasa"

            report = module.build_readiness_report(shadow_dir=shadow_dir)

            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "missing_shadow_files")
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())

    def test_manifest_count_mismatch_is_blocked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow_dir = self.make_shadow_dir(root, items=1, triples_count=2, narratives_count=2)
            manifest_path = shadow_dir / "package_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["triples"] = 99
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = module.build_readiness_report(shadow_dir=shadow_dir)

            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "count_mismatch")

    def test_sample_queries_return_json_results(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow_dir = self.make_shadow_dir(root)

            report = module.build_readiness_report(shadow_dir=shadow_dir, expected_items=1, expected_triples=2, expected_narratives=2)

            self.assertTrue(report["ready"])
            self.assertEqual(report["counts"], {"items": 1, "triples": 2, "narratives": 2})
            self.assertEqual(report["validation"]["triple_validation_status"], {"accepted": 2})
            self.assertEqual(report["validation"]["narrative_source_roles"], {"primary": 2})
            subject_query = next(item for item in report["sample_query_preview"] if item["query_type"] == "subject")
            self.assertEqual(subject_query["result_count"], 2)
            self.assertIn("Apophis", subject_query["results"][0]["subject"])
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())
            self.assertFalse((root / "data" / "chroma_db_shadow").exists())

    def test_output_paths_are_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.make_shadow_dir(root)

            self.assertTrue(module.output_allowed(root / "evaluation" / "four_source_expansion" / "report.json"))
            self.assertTrue(module.output_allowed(root / "docs" / "report.md", allow_docs=True))
            self.assertFalse(module.output_allowed(root / "data" / "triples" / "report.json"))


if __name__ == "__main__":
    unittest.main()

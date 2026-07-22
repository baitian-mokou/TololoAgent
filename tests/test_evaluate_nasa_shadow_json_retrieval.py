import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_nasa_shadow_json_retrieval.py"


def load_module():
    spec = importlib.util.spec_from_file_location("evaluate_nasa_shadow_json_retrieval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NasaShadowJsonRetrievalEvalTests(unittest.TestCase):
    def make_shadow_dir(self, root: Path) -> Path:
        shadow_dir = root / "data" / "triples_shadow" / "nasa"
        shadow_dir.mkdir(parents=True)
        triples = [
            {
                "subject": "Apophis",
                "predicate": "INSTANCE_OF",
                "object": "asteroid",
                "source_url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "source_id": "nasa",
                "validation_status": "accepted",
                "evidence": "Apophis is an asteroid.",
            },
            {
                "subject": "Apophis",
                "predicate": "SOURCE_URL",
                "object": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "source_url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "source_id": "nasa",
                "validation_status": "accepted",
                "evidence": "https://science.nasa.gov/solar-system/asteroids/apophis/",
            },
            {
                "subject": "Bennu",
                "predicate": "HAS_TOPIC",
                "object": "asteroid",
                "source_url": "https://science.nasa.gov/solar-system/asteroids/101955-bennu/",
                "source_id": "nasa",
                "validation_status": "accepted",
                "evidence": "Bennu is an asteroid studied by NASA.",
            },
        ]
        narratives = [
            {
                "page_title": "Apophis - NASA Science",
                "content": "Apophis is a near-Earth asteroid observed by NASA.",
                "source_url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                "source_id": "nasa",
                "source_role": "primary",
            }
        ]
        manifest = {"source_id": "nasa", "items": 2, "triples": 3, "narratives": 1}
        (shadow_dir / "triples_preview.json").write_text(json.dumps(triples), encoding="utf-8")
        (shadow_dir / "narratives_preview.json").write_text(json.dumps(narratives), encoding="utf-8")
        (shadow_dir / "package_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return shadow_dir

    def test_default_eval_cases_are_repeatable(self):
        module = load_module()

        cases = module.default_eval_cases()

        self.assertGreaterEqual(len(cases), 8)
        self.assertLessEqual(len(cases), 12)
        self.assertTrue(all(case["case_id"] for case in cases))
        self.assertTrue(all(case["query"] for case in cases))

    def test_eval_cases_pass_against_fixture(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow_dir = self.make_shadow_dir(root)
            cases = [
                {"case_id": "subject_apophis", "query": "Apophis", "oracle": {"subject": "Apophis", "relation": "INSTANCE_OF", "topic": "asteroid"}},
                {"case_id": "url_apophis", "query": "apophis source", "oracle": {"source_url": "https://science.nasa.gov/solar-system/asteroids/apophis/"}},
                {"case_id": "topic_bennu", "query": "Bennu asteroid", "oracle": {"subject": "Bennu", "topic": "asteroid"}},
            ]

            report = module.build_eval_report(shadow_dir=shadow_dir, cases=cases)

            self.assertTrue(report["ready"])
            self.assertEqual(report["overall"]["total_cases"], 3)
            self.assertEqual(report["overall"]["passed_cases"], 3)
            self.assertEqual(report["overall"]["pass_rate"], 1.0)
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())
            self.assertFalse((root / "data" / "chroma_db_shadow").exists())

    def test_missing_shadow_artifact_is_blocked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            report = module.build_eval_report(shadow_dir=root / "data" / "triples_shadow" / "nasa", cases=module.default_eval_cases())

            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "missing_shadow_files")

    def test_report_outputs_are_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            self.assertTrue(module.output_allowed(root / "evaluation" / "four_source_expansion" / "eval.json"))
            self.assertTrue(module.output_allowed(root / "docs" / "eval.md", allow_docs=True))
            self.assertFalse(module.output_allowed(root / "data" / "triples" / "eval.json"))


if __name__ == "__main__":
    unittest.main()

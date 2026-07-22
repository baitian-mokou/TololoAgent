import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "agent" / "nasa_shadow_review.py"


def load_module():
    spec = importlib.util.spec_from_file_location("nasa_shadow_review", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NasaShadowReviewBypassTests(unittest.TestCase):
    def make_shadow_and_eval(self, root: Path, *, ready: bool = True) -> tuple[Path, Path]:
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
            }
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
        (shadow_dir / "triples_preview.json").write_text(json.dumps(triples), encoding="utf-8")
        (shadow_dir / "narratives_preview.json").write_text(json.dumps(narratives), encoding="utf-8")
        (shadow_dir / "package_manifest.json").write_text(
            json.dumps({"source_id": "nasa", "items": 1, "triples": 1, "narratives": 1}),
            encoding="utf-8",
        )
        eval_path = root / "evaluation" / "four_source_expansion" / "eval.json"
        eval_path.parent.mkdir(parents=True)
        eval_path.write_text(
            json.dumps(
                {
                    "ready": ready,
                    "eval_cases": [
                        {
                            "case_id": "subject_apophis",
                            "query": "Apophis asteroid",
                            "oracle": {"subject": "Apophis", "relation": "INSTANCE_OF", "topic": "asteroid"},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return shadow_dir, eval_path

    def test_default_review_only_false_is_blocked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow_dir, eval_path = self.make_shadow_and_eval(root)

            report = module.run_nasa_shadow_review_preview(
                shadow_dir=shadow_dir,
                eval_report_path=eval_path,
            )

            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "review_only_required")
            self.assertEqual(report["adapter_mappings"], [])
            self.assertFalse((root / "data" / "triples").exists())

    def test_review_only_true_returns_mapping_payloads(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow_dir, eval_path = self.make_shadow_and_eval(root)

            report = module.run_nasa_shadow_review_preview(
                shadow_dir=shadow_dir,
                eval_report_path=eval_path,
                review_only=True,
            )

            self.assertTrue(report["ready"])
            self.assertEqual(report["mapping_count"], 1)
            payload = report["adapter_mappings"][0]["expected_retrieval_payload"]
            self.assertEqual(payload["query"], "Apophis asteroid")
            self.assertEqual(payload["source_id"], "nasa")
            self.assertIn("evidence", payload["top_result"])
            self.assertIn("source_url", payload["top_result"])
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())
            self.assertFalse((root / "data" / "chroma_db_shadow").exists())

    def test_phase48_not_ready_is_blocked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow_dir, eval_path = self.make_shadow_and_eval(root, ready=False)

            report = module.run_nasa_shadow_review_preview(
                shadow_dir=shadow_dir,
                eval_report_path=eval_path,
                review_only=True,
            )

            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "phase48_eval_not_ready")
            self.assertEqual(report["mapping_count"], 0)

    def test_module_does_not_import_database_or_mutate_active_source(self):
        source = MODULE.read_text(encoding="utf-8")

        self.assertNotIn("ChromaStore", source)
        self.assertNotIn("Neo4jLoader", source)
        self.assertNotRegex(source, r"^ACTIVE_SOURCE\s*=")


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preview_nasa_shadow_query_chain_adapter.py"


def load_module():
    spec = importlib.util.spec_from_file_location("preview_nasa_shadow_query_chain_adapter", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NasaShadowQueryChainAdapterPreviewTests(unittest.TestCase):
    def make_shadow_and_eval(self, root: Path) -> tuple[Path, Path]:
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
                    "ready": True,
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

    def test_preview_maps_eval_cases_to_payload_shape(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow_dir, eval_path = self.make_shadow_and_eval(root)

            report = module.build_adapter_preview(shadow_dir=shadow_dir, eval_report_path=eval_path)

            self.assertTrue(report["ready"])
            self.assertEqual(report["mapping_count"], 1)
            payload = report["adapter_mappings"][0]["expected_retrieval_payload"]
            self.assertEqual(payload["query"], "Apophis asteroid")
            self.assertEqual(payload["source_id"], "nasa")
            self.assertGreaterEqual(payload["result_count"], 1)
            self.assertEqual(payload["top_result"]["subject"], "Apophis")
            self.assertIn("evidence", payload["top_result"])
            self.assertIn("source_url", payload["top_result"])
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse((root / "data" / "chroma_db").exists())
            self.assertFalse((root / "data" / "chroma_db_shadow").exists())

    def test_missing_shadow_or_eval_report_is_blocked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            report = module.build_adapter_preview(
                shadow_dir=root / "data" / "triples_shadow" / "nasa",
                eval_report_path=root / "evaluation" / "four_source_expansion" / "missing.json",
            )

            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "missing_shadow_or_eval_report")

    def test_output_paths_are_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            self.assertTrue(module.output_allowed(root / "evaluation" / "four_source_expansion" / "adapter.json"))
            self.assertTrue(module.output_allowed(root / "docs" / "adapter.md", allow_docs=True))
            self.assertFalse(module.output_allowed(root / "data" / "triples" / "adapter.json"))

    def test_script_does_not_import_database_or_mutate_active_source(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("ChromaStore", source)
        self.assertNotIn("Neo4jLoader", source)
        self.assertNotRegex(source, r"^ACTIVE_SOURCE\s*=")


if __name__ == "__main__":
    unittest.main()

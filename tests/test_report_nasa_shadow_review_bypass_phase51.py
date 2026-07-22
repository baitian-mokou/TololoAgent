import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "report_nasa_shadow_review_bypass_phase51.py"


def load_script():
    spec = importlib.util.spec_from_file_location("report_nasa_shadow_review_bypass_phase51", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NasaShadowReviewBypassReportTests(unittest.TestCase):
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

    def test_writes_review_only_report_to_allowed_paths(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow_dir, eval_path = self.make_shadow_and_eval(root)
            out_json = root / "evaluation" / "four_source_expansion" / "phase51.json"
            out_md = root / "docs" / "phase51.md"

            exit_code = module.main(
                [
                    "--shadow-dir",
                    str(shadow_dir),
                    "--eval-report-json",
                    str(eval_path),
                    "--out-json",
                    str(out_json),
                    "--out-md",
                    str(out_md),
                ]
            )

            self.assertEqual(exit_code, 0)
            report = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertTrue(report["ready"])
            self.assertEqual(report["mapping_count"], 1)
            self.assertFalse(report["formal_default_triples_write"])
            self.assertFalse(report["chroma_write"])
            self.assertFalse(report["neo4j_write"])
            self.assertTrue(out_md.exists())
            self.assertFalse((root / "data" / "triples").exists())

    def test_rejects_output_outside_evaluation_or_docs(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow_dir, eval_path = self.make_shadow_and_eval(root)

            exit_code = module.main(
                [
                    "--shadow-dir",
                    str(shadow_dir),
                    "--eval-report-json",
                    str(eval_path),
                    "--out-json",
                    str(root / "data" / "bad.json"),
                    "--out-md",
                    str(root / "docs" / "phase51.md"),
                ]
            )

            self.assertEqual(exit_code, 2)
            self.assertFalse((root / "data" / "bad.json").exists())


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_nasa_shadow_combined_artifact.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_nasa_shadow_combined_artifact", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifyNasaShadowCombinedArtifactTests(unittest.TestCase):
    def make_artifact(self, root: Path, *, triples=2, narratives=2, items=1) -> Path:
        shadow = root / "data" / "triples_shadow" / "nasa"
        shadow.mkdir(parents=True)
        triple_rows = [
            {
                "subject": f"Subject {i}",
                "predicate": "HAS_TOPIC",
                "object": "asteroid",
                "source_id": "nasa",
                "validation_status": "accepted",
                "source_url": f"https://science.nasa.gov/{i}",
                "evidence": "evidence",
            }
            for i in range(triples)
        ]
        narrative_rows = [
            {
                "page_title": f"Subject {i}",
                "content": "NASA narrative",
                "source_id": "nasa",
                "source_role": "primary",
                "source_url": f"https://science.nasa.gov/{i}",
            }
            for i in range(narratives)
        ]
        manifest = {"source_id": "nasa", "items": items, "triples": triples, "narratives": narratives}
        (shadow / "triples_preview.json").write_text(json.dumps(triple_rows), encoding="utf-8")
        (shadow / "narratives_preview.json").write_text(json.dumps(narrative_rows), encoding="utf-8")
        (shadow / "package_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return shadow

    def test_present_artifact_ok(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            shadow = self.make_artifact(Path(temp))
            report = module.verify_artifact(shadow, expected_items=1, expected_triples=2, expected_narratives=2)
            self.assertTrue(report["ready"])
            self.assertEqual(report["counts"], {"items": 1, "triples": 2, "narratives": 2})
            self.assertFalse((Path(temp) / "data" / "triples").exists())

    def test_missing_artifact_blocked_with_rebuild_command(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            report = module.verify_artifact(Path(temp) / "data" / "triples_shadow" / "nasa")
            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "missing_shadow_files")
            self.assertIn("merge_nasa_shadow_packages.py", report["rebuild_command"])

    def test_count_mismatch_blocked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            shadow = self.make_artifact(Path(temp), triples=1)
            report = module.verify_artifact(shadow, expected_items=1, expected_triples=2, expected_narratives=2)
            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "count_mismatch")

    def test_output_paths_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertTrue(module.output_allowed(root / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(root / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(root / "data" / "x.json"))


if __name__ == "__main__":
    unittest.main()

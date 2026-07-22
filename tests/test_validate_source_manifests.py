import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_source_manifests.py"


def load_script():
    spec = importlib.util.spec_from_file_location("validate_source_manifests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ValidateSourceManifestsTests(unittest.TestCase):
    def test_real_and_example_manifests_validate(self):
        module = load_script()

        report = module.validate_manifest_tree(ROOT / "configs" / "source_manifests")

        self.assertTrue(report["passed"])
        self.assertGreaterEqual(report["summary"]["validated"], 7)
        self.assertEqual(report["summary"]["failed"], 0)

    def test_missing_required_field_fails(self):
        module = load_script()
        manifest = {
            "source_name": "broken",
            "source_mode": "academic",
            "allowed_domains": ["example.edu"],
            "seed_urls": ["https://example.edu/science"],
            "quality_gate": {"accepted_min_score": 70, "review_min_score": 40, "allow_exploratory": True, "skip_rejected_allowed": False},
        }

        errors = module.validate_manifest(manifest, Path("broken.json"))

        self.assertIn("missing topic_taxonomy", errors)

    def test_invalid_source_mode_and_threshold_fail(self):
        module = load_script()
        manifest = {
            "source_name": "bad",
            "source_mode": "magic",
            "allowed_domains": ["example.edu"],
            "seed_urls": ["https://example.edu/science"],
            "include_path_keywords": ["science"],
            "exclude_path_keywords": [],
            "topic_taxonomy": ["astronomy"],
            "quality_gate": {"accepted_min_score": 101, "review_min_score": -1, "allow_exploratory": True, "skip_rejected_allowed": False},
            "quality_notes": "bad",
        }

        errors = module.validate_manifest(manifest, Path("bad.json"))

        self.assertTrue(any("invalid source_mode" in error for error in errors))
        self.assertTrue(any("accepted_min_score" in error for error in errors))
        self.assertTrue(any("review_min_score" in error for error in errors))

    def test_entity_data_cannot_skip_rejected(self):
        module = load_script()
        manifest = {
            "source_name": "bad_entity",
            "source_mode": "entity_data",
            "allowed_domains": ["www.wikidata.org"],
            "seed_entities": [{"entity": "Mars", "qid": "Q111"}],
            "include_path_keywords": ["/wiki/Q"],
            "exclude_path_keywords": [],
            "topic_taxonomy": ["astronomy"],
            "quality_gate": {"accepted_min_score": 80, "review_min_score": 20, "allow_exploratory": False, "skip_rejected_allowed": True},
            "quality_notes": "bad",
        }

        errors = module.validate_manifest(manifest, Path("bad_entity.json"))

        self.assertIn("entity_data cannot set skip_rejected_allowed true", errors)

    def test_cli_writes_report(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "report.json"
            code = module.main(["--manifest-dir", str(ROOT / "configs" / "source_manifests"), "--report-json", str(out)])
            payload = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertTrue(payload["passed"])


if __name__ == "__main__":
    unittest.main()

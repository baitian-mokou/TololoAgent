import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sandbox_manifest_candidates.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sandbox_manifest_candidates", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SandboxManifestCandidatesTests(unittest.TestCase):
    def test_unregistered_manifest_writes_only_sandbox_report(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "evaluation" / "source_quality" / "sandbox" / "academic_report.json"
            exit_code = module.main([
                "--manifest",
                str(ROOT / "configs" / "source_manifests" / "examples" / "academic_example.json"),
                "--report-json",
                str(report_path),
            ])

            self.assertEqual(exit_code, 0)
            self.assertTrue(report_path.exists())
            self.assertFalse((root / "data").exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_id"], "academic_example")
            self.assertFalse(payload["registered"])
            self.assertFalse(payload["network"])
            self.assertTrue(payload["manifest_validation"]["passed"])
            self.assertEqual(payload["safety_flags"]["formal_pipeline_write"], False)
            self.assertGreaterEqual(payload["candidate_count"], 3)
            self.assertGreaterEqual(len(payload["triage_counts"]), 2)
            self.assertIn("rejected", payload["triage_counts"])
            self.assertEqual(payload["fixture_candidates_path"], "tests/fixtures/source_quality/academic_example_candidates.json")

    def test_sandbox_rejects_report_outside_evaluation_sandbox(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "data" / "bad.json"
            exit_code = module.main([
                "--manifest",
                str(ROOT / "configs" / "source_manifests" / "examples" / "academic_example.json"),
                "--report-json",
                str(report_path),
            ])

            self.assertEqual(exit_code, 2)
            self.assertFalse(report_path.exists())

    def test_invalid_manifest_fails_before_report(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "bad.json"
            report_path = root / "evaluation" / "source_quality" / "sandbox" / "bad_report.json"
            manifest_path.write_text(json.dumps({"source_name": "bad"}), encoding="utf-8")

            exit_code = module.main([
                "--manifest",
                str(manifest_path),
                "--report-json",
                str(report_path),
            ])

            self.assertEqual(exit_code, 2)
            self.assertFalse(report_path.exists())

    def test_fixture_candidates_are_scored_without_full_body_snapshot(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "evaluation" / "source_quality" / "sandbox" / "fixture_report.json"
            exit_code = module.main([
                "--manifest",
                str(ROOT / "configs" / "source_manifests" / "examples" / "academic_example.json"),
                "--input-json",
                str(ROOT / "tests" / "fixtures" / "page_quality" / "sample_candidates.json"),
                "--report-json",
                str(report_path),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["candidate_count"], 4)
            self.assertTrue(payload["selected_candidate_snapshots"])
            self.assertNotIn("html", payload["selected_candidate_snapshots"][0])
            self.assertNotIn("text", payload["selected_candidate_snapshots"][0])

    def test_script_source_has_no_network_or_delete_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("urllib", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("Remove-Item", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)


if __name__ == "__main__":
    unittest.main()

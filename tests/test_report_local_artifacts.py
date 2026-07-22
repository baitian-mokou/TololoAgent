import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "report_local_artifacts.py"


def load_report_script():
    spec = importlib.util.spec_from_file_location("report_local_artifacts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReportLocalArtifactsTests(unittest.TestCase):
    def test_script_does_not_contain_destructive_file_operations(self):
        source = SCRIPT.read_text(encoding="utf-8")

        for token in ("Remove-Item", "shutil.rmtree", "os.remove", ".unlink(", ".rmdir("):
            self.assertNotIn(token, source)

    def test_iter_artifacts_reports_existing_targets_without_deleting(self):
        module = load_report_script()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "models"
            artifact.mkdir()
            (artifact / "sample.bin").write_bytes(b"1234")

            old_root, old_targets, old_globs = module.ROOT, module.TARGETS, module.GLOBS
            try:
                module.ROOT = root
                module.TARGETS = ["models"]
                module.GLOBS = []

                artifacts = list(module.iter_artifacts())
            finally:
                module.ROOT = old_root
                module.TARGETS = old_targets
                module.GLOBS = old_globs

            self.assertEqual([artifact], artifacts)
            self.assertTrue((artifact / "sample.bin").exists())


if __name__ == "__main__":
    unittest.main()

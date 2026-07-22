import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_production_source_gate.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_production_source_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductionSourceGateTests(unittest.TestCase):
    def test_current_shadow_sources_are_review_ready_not_authorized(self):
        module = load_script()

        report = module.build_report()

        self.assertTrue(report["passed"])
        self.assertEqual(report["decision"], "review_ready_not_authorized")
        self.assertEqual(report["default_source"]["active_source"], "zh_wikipedia")
        self.assertFalse(report["formal_write_authorized"])
        self.assertTrue(all(item["review_ready"] for item in report["sources"].values()))
        self.assertTrue(all(item["registry_state"] == "disabled" for item in report["sources"].values()))
        self.assertTrue(all(item["output_path_limited_to_shadow"] for item in report["sources"].values()))
        self.assertEqual(
            report["test_evidence"],
            ["tests.test_run_production_source_gate", "tests.test_validate_source_manifests"],
        )


if __name__ == "__main__":
    unittest.main()

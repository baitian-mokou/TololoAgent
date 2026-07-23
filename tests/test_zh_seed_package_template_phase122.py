import json
import tempfile
import unittest
from pathlib import Path

from scripts import zh_seed_package_template_phase122 as phase122


class Phase122ZhSeedPackageTemplateTest(unittest.TestCase):
    def test_template_includes_required_fields(self):
        template = phase122.seed_template()
        for field in phase122.REQUIRED_FIELDS:
            self.assertIn(field, template)
        self.assertIn("provenance_notes", template)
        self.assertIn("expected_sha256", template)

    def test_placeholder_body_cannot_be_accepted(self):
        result = phase122.validate_template(phase122.seed_template())
        self.assertFalse(result["accepted_as_real_seed"])
        self.assertIn("placeholder_body", result["warnings"])

    def test_summary_flags_false(self):
        summary = phase122.build_summary()
        self.assertFalse(summary["production_ready"])
        self.assertFalse(summary["preflight_allowed"])
        self.assertFalse(summary["apply_approved"])
        self.assertFalse(summary["ingest_approved"])
        self.assertFalse(summary["queue_allowed"])
        self.assertFalse(summary["live_fetch_used"])

    def test_output_guard_and_no_default_paths(self):
        self.assertFalse(phase122.output_allowed(Path(tempfile.gettempdir()) / "phase122.json"))
        self.assertFalse(phase122.output_allowed(phase122.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase122.output_allowed(phase122.ROOT / "evaluation" / "four_source_expansion" / "phase122" / "x.json"))
        self.assertTrue(phase122.output_allowed(phase122.ROOT / "docs" / "phase122.md", allow_docs=True))
        self.assertFalse(any(str(path).startswith("data/") for path in phase122.output_files()))

    def test_template_json_round_trips(self):
        template = phase122.seed_template()
        self.assertEqual(json.loads(json.dumps(template, ensure_ascii=False))["title"], template["title"])


if __name__ == "__main__":
    unittest.main()

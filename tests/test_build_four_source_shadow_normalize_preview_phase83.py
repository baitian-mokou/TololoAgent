import json
import tempfile
import unittest
from pathlib import Path


class Phase83ShadowNormalizePreviewTests(unittest.TestCase):
    def test_succeeded_only_quality_gate_and_no_data_write(self):
        from scripts import build_four_source_shadow_normalize_preview_phase83 as phase83

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report_path = root / "evaluation" / "four_source_expansion" / "phase82" / "report.json"
            report_path.parent.mkdir(parents=True)
            report_path.write_text(
                json.dumps(
                    {
                        "raw_previews": [
                            {"source": "nasa", "title": "Mars", "url": "https://science.nasa.gov/mars", "fetched": True, "status": "http_200", "text_excerpt": "Mars is a planet.", "quality_flags": {"allowlisted": True}},
                            {"source": "nasa", "title": "Failed", "url": "https://science.nasa.gov/fail", "fetched": False, "status": "failed", "text_excerpt": ""},
                            {"source": "esa", "title": "Empty", "url": "https://www.esa.int/empty", "fetched": True, "status": "http_200", "text_excerpt": ""},
                            {"source": "wikidata", "title": "Mars", "entity_id": "Q111", "url": "https://www.wikidata.org/wiki/Q111", "fetched": True, "status": "assessment_preview", "claims_subset": "qid Q111 Mars planet", "quality_flags": {"allowlisted": True}},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            report = phase83.build_report(report_path=report_path, root=root)
            self.assertEqual(report["input_succeeded"], 3)
            self.assertEqual(report["normalized"], 2)
            self.assertEqual(report["rejected"], 1)
            self.assertEqual(report["triples"], 4)
            self.assertEqual(report["narratives"], 2)
            self.assertFalse((root / "data").exists())
            for record in report["normalized_records"]:
                self.assertTrue(record["source"])
                self.assertTrue(record["source_url"] or record["entity_id"])
                self.assertEqual(record["schema_version"], "phase83_shadow_normalize_preview_v1")

    def test_output_path_restricted(self):
        from scripts import build_four_source_shadow_normalize_preview_phase83 as phase83

        self.assertTrue(phase83.output_allowed(phase83.ROOT / "evaluation" / "four_source_expansion" / "phase83" / "x.json"))
        self.assertTrue(phase83.output_allowed(phase83.ROOT / "docs" / "x.md", allow_docs=True))
        self.assertFalse(phase83.output_allowed(phase83.ROOT / "data" / "x.json"))
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(phase83.output_allowed(Path(temp) / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

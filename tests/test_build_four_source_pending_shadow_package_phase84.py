import json
import tempfile
import unittest
from pathlib import Path


class Phase84PendingShadowPackageTests(unittest.TestCase):
    def test_builds_pending_package_from_normalized_only(self):
        from scripts import build_four_source_pending_shadow_package_phase84 as phase84

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            phase83 = root / "evaluation" / "four_source_expansion" / "phase83" / "report.json"
            phase83.parent.mkdir(parents=True)
            phase83.write_text(
                json.dumps(
                    {
                        "normalized_records": [
                            {"source": "esa", "title": "Rosetta", "source_url": "https://www.esa.int/rosetta", "entity_id": "", "schema_version": "phase83_shadow_normalize_preview_v1", "provenance": {"phase82_status": "local_preview"}},
                            {"source": "wikidata", "title": "火星", "source_url": "https://www.wikidata.org/wiki/Q111", "entity_id": "Q111", "schema_version": "phase83_shadow_normalize_preview_v1", "provenance": {"phase82_status": "assessment_preview"}},
                        ],
                        "triples_preview": [
                            {"source_id": "esa", "subject": "Rosetta", "predicate": "SOURCE_URL", "object": "https://www.esa.int/rosetta", "schema_version": "phase83_shadow_normalize_preview_v1", "provenance": {"phase82_status": "local_preview"}},
                            {"source_id": "wikidata", "subject": "火星", "predicate": "SOURCE_URL", "object": "https://www.wikidata.org/wiki/Q111", "schema_version": "phase83_shadow_normalize_preview_v1", "provenance": {"phase82_status": "assessment_preview"}},
                        ],
                        "narratives_preview": [
                            {"source_id": "esa", "title": "Rosetta", "schema_version": "phase83_shadow_normalize_preview_v1", "provenance": {"phase82_status": "local_preview"}},
                            {"source_id": "wikidata", "title": "火星", "schema_version": "phase83_shadow_normalize_preview_v1", "provenance": {"phase82_status": "assessment_preview"}},
                        ],
                        "rejected_records": [{"source": "nasa", "title": "Bad", "reason": "empty_text_or_claim"}],
                    }
                ),
                encoding="utf-8",
            )
            report = phase84.build_package(phase83_report=phase83, root=root)
            self.assertEqual(report["manifest"]["approval_status"], "pending_review")
            self.assertEqual(report["manifest"]["items"], 2)
            self.assertEqual(report["manifest"]["triples"], 2)
            self.assertEqual(report["manifest"]["narratives"], 2)
            self.assertEqual(report["manifest"]["rejected_reference_count"], 1)
            self.assertEqual(report["manifest"]["source_breakdown"], {"esa": 1, "wikidata": 1})
            self.assertEqual(report["integrity"]["errors"], [])
            self.assertFalse((root / "data").exists())

    def test_output_path_restricted(self):
        from scripts import build_four_source_pending_shadow_package_phase84 as phase84

        self.assertTrue(phase84.output_allowed(phase84.ROOT / "evaluation" / "four_source_expansion" / "phase84" / "x.json"))
        self.assertTrue(phase84.output_allowed(phase84.ROOT / "docs" / "x.md", allow_docs=True))
        self.assertFalse(phase84.output_allowed(phase84.ROOT / "data" / "x.json"))
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(phase84.output_allowed(Path(temp) / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

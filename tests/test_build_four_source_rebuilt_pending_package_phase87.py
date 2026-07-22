import json
import tempfile
import unittest
from pathlib import Path


class Phase87RebuiltPendingPackageTests(unittest.TestCase):
    def test_rebuilds_four_source_package_without_failed_or_unrepaired(self):
        from scripts import build_four_source_rebuilt_pending_package_phase87 as phase87

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p83 = root / "evaluation" / "four_source_expansion" / "phase83" / "p83.json"
            p86 = root / "evaluation" / "four_source_expansion" / "phase86" / "p86.json"
            p83.parent.mkdir(parents=True)
            p86.parent.mkdir(parents=True)
            p83.write_text(
                json.dumps(
                    {
                        "normalized_records": [
                            {"source": "zh_wikipedia", "source_id": "zh_wikipedia", "title": "太阳", "subject": "太阳", "source_url": "https://zh.wikipedia.org/wiki/太阳", "entity_id": "", "schema_version": "p83", "extraction_method": "x", "confidence": 0.7, "quality_flags": {"ok": True}, "provenance": {"p": "83"}, "text_excerpt": "太阳"},
                            {"source": "esa", "source_id": "esa", "title": "Rosetta", "subject": "Rosetta", "source_url": "https://www.esa.int/rosetta", "entity_id": "", "schema_version": "p83", "extraction_method": "x", "confidence": 0.7, "quality_flags": {"ok": True}, "provenance": {"p": "83"}, "text_excerpt": "Rosetta"},
                            {"source": "wikidata", "source_id": "wikidata", "title": "火星", "subject": "火星", "source_url": "https://www.wikidata.org/wiki/Q111", "entity_id": "Q111", "schema_version": "p83", "extraction_method": "x", "confidence": 0.7, "quality_flags": {"ok": True}, "provenance": {"p": "83"}, "text_excerpt": "火星"},
                        ],
                        "rejected_records": [{"source": "nasa", "title": "Bad", "reason": "missing_source_metadata"}],
                    }
                ),
                encoding="utf-8",
            )
            p86.write_text(
                json.dumps(
                    {
                        "repaired_candidates": [
                            {"source": "nasa", "source_id": "nasa", "title": "Juno", "source_url": "https://science.nasa.gov/mission/juno", "entity_id": "", "schema_version": "p86", "repair_reason": "fixed", "text_excerpt": "Juno text", "quality_flags": {"metadata_repaired": True}, "provenance": {"p": "86"}}
                        ],
                        "remaining_failure_records": [{"url": "https://science.nasa.gov/failed", "reason": "missing_title"}],
                    }
                ),
                encoding="utf-8",
            )
            report = phase87.build_package(phase83_report=p83, phase86_report=p86, root=root)
            self.assertEqual(report["manifest"]["approval_status"], "pending_review")
            self.assertFalse(report["production_ready"])
            self.assertEqual(report["manifest"]["source_breakdown"], {"esa": 1, "nasa": 1, "wikidata": 1, "zh_wikipedia": 1})
            self.assertEqual(report["manifest"]["items"], 4)
            self.assertEqual(report["manifest"]["triples"], 8)
            self.assertEqual(report["integrity"]["errors"], [])
            self.assertEqual(report["integrity"]["failed_or_unrepaired_included"], False)
            self.assertFalse((root / "data").exists())

    def test_output_path_restricted(self):
        from scripts import build_four_source_rebuilt_pending_package_phase87 as phase87

        self.assertTrue(phase87.output_allowed(phase87.ROOT / "evaluation" / "four_source_expansion" / "phase87" / "x.json"))
        self.assertTrue(phase87.output_allowed(phase87.ROOT / "docs" / "x.md", allow_docs=True))
        self.assertFalse(phase87.output_allowed(phase87.ROOT / "data" / "x.json"))
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(phase87.output_allowed(Path(temp) / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

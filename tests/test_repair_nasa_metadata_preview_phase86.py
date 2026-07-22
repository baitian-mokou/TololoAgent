import json
import tempfile
import unittest
from pathlib import Path


class Phase86NasaMetadataRepairTests(unittest.TestCase):
    def test_repairs_only_succeeded_nasa_with_url_and_title_signal(self):
        from scripts import repair_nasa_metadata_preview_phase86 as phase86

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p82 = root / "evaluation" / "four_source_expansion" / "phase82" / "p82.json"
            p83 = root / "evaluation" / "four_source_expansion" / "phase83" / "p83.json"
            p82.parent.mkdir(parents=True)
            p83.parent.mkdir(parents=True)
            p82.write_text(
                json.dumps(
                    {
                        "raw_previews": [
                            {"source": "nasa", "title": "", "url": "https://science.nasa.gov/mission/juno", "fetched": True, "status": "http_200", "text_excerpt": "Juno - NASA Science Explore Search"},
                            {"source": "nasa", "title": "", "url": "https://science.nasa.gov/failed", "fetched": False, "status": "failed", "text_excerpt": ""},
                            {"source": "nasa", "title": "", "url": "", "fetched": True, "status": "http_200", "text_excerpt": "No URL - NASA Science"},
                            {"source": "esa", "title": "Rosetta", "url": "https://www.esa.int/rosetta", "fetched": True, "status": "http_200", "text_excerpt": "Rosetta"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            p83.write_text(json.dumps({"rejected_records": [{"source": "nasa", "title": "", "reason": "missing_source_metadata"}]}), encoding="utf-8")
            report = phase86.build_report(phase82_report=p82, phase83_report=p83, root=root)
            self.assertEqual(report["nasa_succeeded_phase82"], 2)
            self.assertEqual(report["repaired_count"], 1)
            self.assertEqual(report["passed_normalize_gate"], 1)
            self.assertEqual(report["remaining_failures"], 1)
            repaired = report["repaired_candidates"][0]
            self.assertEqual(repaired["source"], "nasa")
            self.assertEqual(repaired["title"], "Juno")
            self.assertTrue(repaired["source_url"])
            self.assertTrue(repaired["provenance"])
            self.assertFalse((root / "data").exists())

    def test_output_path_restricted(self):
        from scripts import repair_nasa_metadata_preview_phase86 as phase86

        self.assertTrue(phase86.output_allowed(phase86.ROOT / "evaluation" / "four_source_expansion" / "phase86" / "x.json"))
        self.assertTrue(phase86.output_allowed(phase86.ROOT / "docs" / "x.md", allow_docs=True))
        self.assertFalse(phase86.output_allowed(phase86.ROOT / "data" / "x.json"))
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(phase86.output_allowed(Path(temp) / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

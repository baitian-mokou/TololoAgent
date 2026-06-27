import json
import tempfile
import unittest
from pathlib import Path

from src.source_adapters.nasa import NasaPipelineAdapter
from src.source_adapters.wikidata import WikidataFixtureAdapter


class LivePreviewReportTests(unittest.TestCase):
    def test_wikidata_live_preview_report_uses_mocked_fetch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / "wikidata_live_preview_report.json"
            adapter = WikidataFixtureAdapter(
                mode="live",
                base_dir=str(root),
                raw_json_dir=str(root / "raw"),
                triples_dir=str(root / "triples"),
            )
            adapter.fetch_live = lambda: {
                "fetched_at": "2026-01-01T00:00:00+00:00",
                "entities": {
                    "Q111": {
                        "labels": {"zh": {"value": "火星"}},
                        "claims": {
                            "P397": [{
                                "id": "Q111$orbit",
                                "mainsnak": {"datavalue": {"value": {"id": "Q525"}}},
                            }],
                            "P2067": [{
                                "id": "Q111$mass",
                                "mainsnak": {"datavalue": {"value": {"amount": "+6.4171e23", "unit": "http://www.wikidata.org/entity/Q11570"}}},
                            }],
                        },
                    }
                },
            }

            report = adapter.materialize(str(output))

            self.assertTrue(output.exists())
            self.assertEqual(report["mode"], "live")
            self.assertEqual(report["fetch"]["status"], "ok")
            self.assertFalse(report["preview"]["official_triples_written"])
            facts = report["preview"]["sample_records"][0]["triples"]
            self.assertEqual({fact["relation"] for fact in facts}, {"ORBITS", "HAS_MASS"})
            self.assertIn("source_record_id", facts[0])

    def test_nasa_dry_run_report_uses_offline_raw_without_network(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_dir = root / "raw" / "nasa"
            raw_dir.mkdir(parents=True)
            (raw_dir / "火星_html.json").write_text(json.dumps({
                "title": "火星",
                "url": "https://science.nasa.gov/mars/facts/",
                "text": "根据 NASA Mars Fact Sheet，火星大气主要成分是二氧化碳，另含氮气、氩气。",
                "source": "nasa",
                "source_name": "nasa",
            }, ensure_ascii=False), encoding="utf-8")
            output = root / "nasa_live_preview_report.json"
            adapter = NasaPipelineAdapter(
                mode="dry-run",
                base_dir=str(root),
                raw_json_dir=str(root / "raw"),
                triples_dir=str(root / "triples"),
            )
            adapter.fetch_live = lambda: (_ for _ in ()).throw(RuntimeError("network unavailable"))

            report = adapter.materialize(str(output))

            self.assertEqual(report["fetch"]["status"], "fallback")
            self.assertFalse(report["preview"]["official_triples_written"])
            facts = report["preview"]["sample_records"][0]["triples"]
            self.assertEqual(facts[0]["relation"], "HAS_ATMOSPHERE")
            self.assertIn("source_url", facts[0])


if __name__ == "__main__":
    unittest.main()

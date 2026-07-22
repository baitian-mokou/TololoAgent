import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_manifest_raw_records.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_manifest_raw_records", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MaterializeManifestRawRecordsTests(unittest.TestCase):
    def test_nasa_fact_html_generates_narrative_and_numeric_triples(self):
        module = load_module()
        raw = {
            "title": "Mars Fact Sheet",
            "url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
            "html": """
            <html><body>
            <table>
              <tr><td>Mass (10^24 kg)</td><td>0.64171</td></tr>
              <tr><td>Mean radius (km)</td><td>3389.5</td></tr>
              <tr><td>Atmospheric composition</td><td>Carbon dioxide; Nitrogen</td></tr>
            </table>
            <p>Mars is the fourth planet from the Sun.</p>
            </body></html>
            """,
        }

        record = module.convert_raw_payload("nasa", raw)

        self.assertTrue(record["narratives"])
        triples = {(item["relation"], item["object"]) for item in record["triples"]}
        self.assertIn(("HAS_MASS", "0.64171 10^24 kg"), triples)
        self.assertIn(("HAS_RADIUS", "3389.5 km"), triples)
        self.assertIn(("HAS_ATMOSPHERE", "Carbon dioxide; Nitrogen"), triples)
        self.assertEqual(record["triples"][0]["source_name"], "nasa")
        self.assertEqual(record["triples"][0]["schema_version"], "nasa_shadow_ready_v1")
        self.assertEqual(record["narratives"][0]["source_url"], raw["url"])

    def test_esa_mission_text_generates_mission_target_triple(self):
        module = load_module()
        raw = {
            "title": "ESA - Juice",
            "url": "https://www.esa.int/Science_Exploration/Space_Science/Juice",
            "text": "Juice will explore Jupiter and its icy moons Ganymede, Europa and Callisto.",
        }

        record = module.convert_raw_payload("esa", raw)

        triples = {(item["relation"], item["object"]) for item in record["triples"]}
        self.assertIn(("OPERATED_BY", "ESA"), triples)
        self.assertIn(("HAS_MISSION_TARGET", "Jupiter"), triples)
        self.assertTrue(record["narratives"])

    def test_wikidata_entity_claims_map_core_relations(self):
        module = load_module()
        raw = {
            "title": "Mars",
            "qid": "Q111",
            "source_url": "https://www.wikidata.org/wiki/Q111",
            "entity": {
                "labels": {"en": {"value": "Mars"}},
                "descriptions": {"en": {"value": "fourth planet from the Sun"}},
                "claims": {
                    "P2067": [{
                        "mainsnak": {
                            "datavalue": {
                                "value": {
                                    "amount": "+6.4171",
                                    "unit": "http://www.wikidata.org/entity/Q613726",
                                }
                            }
                        }
                    }],
                    "P397": [{
                        "mainsnak": {
                            "datavalue": {"value": {"id": "Q525"}}
                        }
                    }],
                },
            },
        }

        record = module.convert_raw_payload("wikidata", raw)

        triples = {(item["relation"], item["object"]) for item in record["triples"]}
        self.assertIn(("HAS_MASS", "6.4171 Q613726"), triples)
        self.assertIn(("ORBITS", "Q525"), triples)
        self.assertEqual(record["narratives"][0]["source_name"], "wikidata")

    def test_empty_text_is_skipped(self):
        module = load_module()

        record = module.convert_raw_payload("nasa", {"title": "Empty", "url": "https://science.nasa.gov/empty", "html": ""})

        self.assertEqual(record["narratives"], [])
        self.assertEqual(record["triples"], [])

    def test_materialize_source_writes_outputs_without_cleanup_or_network(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_dir = root / "data" / "raw_json" / "nasa"
            raw_dir.mkdir(parents=True)
            (raw_dir / "mars.json").write_text(json.dumps({
                "title": "Mars Fact Sheet",
                "url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
                "html": "<p>Mars is a planet.</p><table><tr><td>Mean radius (km)</td><td>3389.5</td></tr></table>",
            }, ensure_ascii=False), encoding="utf-8")
            report_path = root / "evaluation" / "ingestion" / "nasa_manifest_materialization_report.json"

            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network disabled")), mock.patch(
                "scripts.ingest_solar_system_sources.clear_source_ingestion_outputs"
            ) as cleanup:
                report = module.materialize_source(
                    "nasa",
                    limit=10,
                    raw_root=root / "data" / "raw_json",
                    triples_root=root / "data" / "triples",
                    report_path=report_path,
                )

            cleanup.assert_not_called()
            self.assertEqual(report["raw_processed"], 1)
            self.assertEqual(report["narratives_written"], 1)
            self.assertTrue(list((root / "data" / "triples" / "nasa").glob("*_triples.json")))
            self.assertTrue(list((root / "data" / "triples" / "nasa").glob("*_narratives.json")))
            self.assertTrue(report_path.exists())


if __name__ == "__main__":
    unittest.main()

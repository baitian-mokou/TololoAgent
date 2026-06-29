import json
import tempfile
import unittest
from pathlib import Path

from src.nlp.nlp_pipeline import NlpPipeline
from src.nlp.preprocess import WikiPreprocessor
from src.nlp.triple_builder import TripleBuilder


class NlpPipelineSourceTests(unittest.TestCase):
    def _make_pipeline(self, source_name: str, raw_dir: Path, triples_dir: Path) -> NlpPipeline:
        pipeline = NlpPipeline(source_name=source_name)
        pipeline.raw_json_dir = str(raw_dir)
        pipeline.triples_dir = str(triples_dir)
        pipeline.triple_builder = TripleBuilder(str(triples_dir))
        return pipeline

    def test_wikidata_raw_json_without_html_is_processed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_dir = root / "raw"
            triples_dir = root / "triples"
            raw_dir.mkdir(parents=True)
            triples_dir.mkdir(parents=True)
            (raw_dir / "Q111.json").write_text(json.dumps({
                "entities": {
                    "Q111": {
                        "id": "Q111",
                        "labels": {"zh": {"value": "火星"}},
                        "claims": {
                            "P397": [{
                                "id": "Q111$orbit",
                                "mainsnak": {"datavalue": {"value": {"id": "Q2"}}},
                            }]
                        },
                    }
                }
            }, ensure_ascii=False), encoding="utf-8")

            pipeline = self._make_pipeline("wikidata", raw_dir, triples_dir)
            triples, narratives = pipeline.process_all()

            self.assertEqual(triples, 1)
            self.assertEqual(narratives, 1)
            saved_triples = json.loads((triples_dir / "火星_triples.json").read_text(encoding="utf-8"))
            saved_narratives = json.loads((triples_dir / "火星_narratives.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_triples[0]["source_name"], "wikidata")
            self.assertEqual(saved_narratives[0]["source_name"], "wikidata")

    def test_wikidata_fixture_wrapper_record_is_processed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_dir = root / "raw"
            triples_dir = root / "triples"
            raw_dir.mkdir(parents=True)
            triples_dir.mkdir(parents=True)
            (raw_dir / "Q2.json").write_text(json.dumps({
                "record": {
                    "title": "地球",
                    "triples": [{"relation": "ORBITS", "object": "太阳"}],
                    "narratives": [{"section": "概览", "content": "地球围绕太阳运行。", "keywords": ["地球", "太阳"]}],
                },
                "fixture_source": "solar_system_fixture.json",
            }, ensure_ascii=False), encoding="utf-8")

            pipeline = self._make_pipeline("wikidata", raw_dir, triples_dir)
            triples, narratives = pipeline.process_all()

            self.assertEqual(triples, 1)
            self.assertEqual(narratives, 1)
            saved_triples = json.loads((triples_dir / "地球_triples.json").read_text(encoding="utf-8"))
            saved_narratives = json.loads((triples_dir / "地球_narratives.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_triples[0]["source_name"], "wikidata")
            self.assertEqual(saved_narratives[0]["source_name"], "wikidata")

    def test_nasa_raw_json_is_processed_via_source_adapter_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_dir = root / "raw"
            triples_dir = root / "triples"
            raw_dir.mkdir(parents=True)
            triples_dir.mkdir(parents=True)
            (raw_dir / "mars_fact.json").write_text(json.dumps({
                "title": "火星",
                "source_url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
                "html": "<table><tr><th>Field</th><th>Mars</th></tr><tr><td>Mass (10^24 kg)</td><td>0.64171</td></tr><tr><td>Mean radius (km)</td><td>3389.5</td></tr></table>",
            }, ensure_ascii=False), encoding="utf-8")

            pipeline = self._make_pipeline("nasa", raw_dir, triples_dir)
            triples, narratives = pipeline.process_all()

            self.assertGreaterEqual(triples, 1)
            self.assertEqual(narratives, 1)
            saved_triples = json.loads((triples_dir / "火星_triples.json").read_text(encoding="utf-8"))
            saved_narratives = json.loads((triples_dir / "火星_narratives.json").read_text(encoding="utf-8"))
            self.assertTrue(all(item["source_name"] == "nasa" for item in saved_triples))
            self.assertEqual(saved_narratives[0]["source_name"], "nasa")

    def test_nasa_fixture_wrapper_record_is_processed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_dir = root / "raw"
            triples_dir = root / "triples"
            raw_dir.mkdir(parents=True)
            triples_dir.mkdir(parents=True)
            (raw_dir / "earth.json").write_text(json.dumps({
                "record": {
                    "title": "地球",
                    "triples": [{"relation": "HAS_RADIUS", "object": "6371 km"}],
                    "narratives": [{"section": "概览", "content": "NASA fixture 提供地球半径。", "keywords": ["地球", "NASA"]}],
                }
            }, ensure_ascii=False), encoding="utf-8")

            pipeline = self._make_pipeline("nasa", raw_dir, triples_dir)
            triples, narratives = pipeline.process_all()

            self.assertEqual(triples, 1)
            self.assertEqual(narratives, 1)
            saved_triples = json.loads((triples_dir / "地球_triples.json").read_text(encoding="utf-8"))
            saved_narratives = json.loads((triples_dir / "地球_narratives.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_triples[0]["source_name"], "nasa")
            self.assertEqual(saved_narratives[0]["source_name"], "nasa")

    def test_esa_raw_json_is_processed_via_source_specific_html_normalization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_dir = root / "raw"
            triples_dir = root / "triples"
            raw_dir.mkdir(parents=True)
            triples_dir.mkdir(parents=True)
            (raw_dir / "JUICE.json").write_text(json.dumps({
                "title": "JUICE",
                "url": "https://www.esa.int/Science_Exploration/Space_Science/Juice",
                "html": "<html><head><title>JUICE</title></head><body>JUICE mission to Jupiter, Europa, Ganymede and Callisto.</body></html>",
                "discovery_depth": 1,
            }, ensure_ascii=False), encoding="utf-8")

            pipeline = self._make_pipeline("esa", raw_dir, triples_dir)
            triples, narratives = pipeline.process_all()

            self.assertGreaterEqual(triples, 0)
            self.assertEqual(narratives, 1)
            saved_narratives = json.loads((triples_dir / "JUICE_narratives.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_narratives[0]["source_name"], "esa")

    def test_esa_fixture_wrapper_record_is_processed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_dir = root / "raw"
            triples_dir = root / "triples"
            raw_dir.mkdir(parents=True)
            triples_dir.mkdir(parents=True)
            (raw_dir / "JUICE.json").write_text(json.dumps({
                "record": {
                    "title": "JUICE",
                    "triples": [{"relation": "HAS_MISSION_TARGET", "object": "木星"}],
                    "narratives": [{"section": "任务", "content": "JUICE 指向木星系统。", "keywords": ["JUICE", "木星"]}],
                },
                "fixture_source": "smoke_fixture.json",
            }, ensure_ascii=False), encoding="utf-8")

            pipeline = self._make_pipeline("esa", raw_dir, triples_dir)
            triples, narratives = pipeline.process_all()

            self.assertGreaterEqual(triples, 0)
            self.assertEqual(narratives, 1)
            saved_narratives = json.loads((triples_dir / "JUICE_narratives.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_narratives[0]["source_name"], "esa")

    def test_zh_infobox_plus_minus_radius_prefers_primary_value(self):
        normalized = WikiPreprocessor._normalize_infobox_object("HAS_RADIUS", "2,440.7 ± 1.0 km 0.387 地球半径")
        self.assertEqual(normalized, "2440.7 km")


if __name__ == "__main__":
    unittest.main()

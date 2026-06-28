import json
import tempfile
import unittest
from pathlib import Path

from scripts.ingest_solar_system_sources import (
    RAW_SOURCES,
    ControlledSourceConfig,
    ingest_records_for_source,
    is_allowed_source_url,
    limit_seed_items,
)


class IngestSolarSystemSourcesTests(unittest.TestCase):
    def test_limit_is_applied_to_seed_items(self):
        seeds = ["a", "b", "c"]
        self.assertEqual(limit_seed_items(seeds, 2), ["a", "b"])
        self.assertEqual(limit_seed_items(seeds, 20), seeds)

    def test_non_allowlist_url_is_rejected(self):
        config = ControlledSourceConfig(
            source_name="nasa",
            allowed_domains=("science.nasa.gov", "nssdc.gsfc.nasa.gov"),
            seed_items=[],
        )

        self.assertTrue(is_allowed_source_url(config, "https://science.nasa.gov/mars/facts/"))
        self.assertFalse(is_allowed_source_url(config, "https://example.com/mars"))

    def test_cross_domain_url_is_rejected_even_if_path_looks_valid(self):
        config = ControlledSourceConfig(
            source_name="esa",
            allowed_domains=("www.esa.int",),
            seed_items=[],
        )

        self.assertFalse(is_allowed_source_url(config, "https://science.nasa.gov/solar-system/juice"))

    def test_raw_json_is_written_into_source_specific_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_root = root / "data" / "raw_json"
            triples_root = root / "data" / "triples"
            evaluation_root = root / "evaluation" / "ingestion"

            report = ingest_records_for_source(
                source_name="wikidata",
                records=[{
                    "raw_id": "mars",
                    "raw_payload": {"title": "火星", "qid": "Q111"},
                    "title": "火星",
                    "triples": [{"subject": "火星", "relation": "HAS_MASS", "object": "6.4171e23 kg"}],
                    "narratives": [{"section": "概述", "content": "火星是太阳系行星。"}],
                    "source_url": "https://www.wikidata.org/wiki/Q111",
                }],
                base_dir=str(root),
                raw_root=str(raw_root),
                triples_root=str(triples_root),
                evaluation_root=str(evaluation_root),
                materialize_graph=False,
                materialize_chroma=False,
            )

            raw_dir = raw_root / "wikidata"
            raw_files = sorted(raw_dir.glob("*.json"))
            self.assertEqual(len(raw_files), 1)
            payload = json.loads(raw_files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["title"], "火星")
            self.assertEqual(report["raw_records_written"], 1)
            self.assertEqual(report["triples_written"], 1)
            self.assertEqual(report["narratives_written"], 1)

    def test_all_known_sources_are_declared(self):
        self.assertEqual(sorted(RAW_SOURCES), ["esa", "nasa", "wikidata", "zh_wikipedia"])


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

import config
from scripts.ingest_solar_system_sources import ESA_MISSION_SEEDS, RAW_SOURCES, WIKIDATA_SEEDS, ensure_raw_source_directories


class RawSourceDirectoriesTests(unittest.TestCase):
    def test_raw_source_directories_are_created_for_all_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "data" / "raw_json"

            created = ensure_raw_source_directories(str(root))

            self.assertEqual(sorted(created.keys()), sorted(RAW_SOURCES))
            for source_name, path in created.items():
                self.assertTrue(Path(path).is_dir(), source_name)
                self.assertEqual(Path(path).name, source_name)

    def test_active_source_remains_zh_wikipedia(self):
        self.assertEqual(config.ACTIVE_SOURCE, "zh_wikipedia")

    def test_wikidata_seeds_cover_owner_approved_expansion_entities(self):
        seeded = {item["entity"] for item in WIKIDATA_SEEDS}

        self.assertTrue({"土卫二", "阋神星", "鸟神星", "妊神星", "冥卫一"}.issubset(seeded))

    def test_esa_seeds_cover_smoke_fixture_orbit_missions(self):
        seeded = {item["title"] for item in ESA_MISSION_SEEDS}

        self.assertTrue({"火星快车号", "金星快车号", "SMART-1"}.issubset(seeded))


if __name__ == "__main__":
    unittest.main()

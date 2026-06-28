import tempfile
import unittest
from pathlib import Path

import config
from scripts.ingest_solar_system_sources import RAW_SOURCES, ensure_raw_source_directories


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


if __name__ == "__main__":
    unittest.main()

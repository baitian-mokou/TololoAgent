import json
import os
import tempfile
import unittest
from pathlib import Path

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from src.agent.llm_agent import LLMAgent
from src.source_adapters.wikidata import WikidataFixtureAdapter


def write_fixture(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "records": [{
            "title": "火星",
            "triples": [{"relation": "ORBITS", "object": "太阳"}],
            "narratives": [{"content": "火星绕太阳运行。"}],
        }]
    }, ensure_ascii=False), encoding="utf-8")


class SourceAdapterModeTests(unittest.TestCase):
    def test_default_mode_is_offline_and_writes_source_namespace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fixture = root / "fixture.json"
            write_fixture(fixture)
            output = root / "report.json"

            adapter = WikidataFixtureAdapter(
                fixture_path=str(fixture),
                base_dir=str(root),
                raw_json_dir=str(root / "raw"),
                triples_dir=str(root / "triples"),
            )
            report = adapter.materialize(str(output))

            self.assertEqual(adapter.mode, "offline")
            self.assertTrue((root / "triples" / "wikidata" / "火星_triples.json").exists())
            self.assertEqual(report["mode"], "offline")
            self.assertTrue(report["preview"]["official_triples_written"])

    def test_dry_run_falls_back_without_writing_official_triples(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fixture = root / "fixture.json"
            write_fixture(fixture)
            output = root / "preview.json"

            adapter = WikidataFixtureAdapter(
                fixture_path=str(fixture),
                mode="dry-run",
                base_dir=str(root),
                raw_json_dir=str(root / "raw"),
                triples_dir=str(root / "triples"),
            )
            adapter.fetch_live = lambda: (_ for _ in ()).throw(RuntimeError("network unavailable"))
            report = adapter.materialize(str(output))

            self.assertEqual(report["fetch"]["status"], "fallback")
            self.assertFalse((root / "triples" / "wikidata" / "火星_triples.json").exists())
            self.assertFalse(report["preview"]["official_triples_written"])
            self.assertTrue(report["graph"]["skipped"])
            self.assertTrue(report["chroma"]["skipped"])

    def test_default_llm_agent_uses_zh_wikipedia(self):
        agent = LLMAgent()

        self.assertEqual(ACTIVE_SOURCE, "zh_wikipedia")
        self.assertEqual(SOURCE_REGISTRY["wikidata"], "disabled")
        self.assertEqual(SOURCE_REGISTRY["nasa"], "disabled")
        self.assertEqual(SOURCE_REGISTRY["esa"], "disabled")
        self.assertEqual(agent.source_name, "zh_wikipedia")


if __name__ == "__main__":
    unittest.main()

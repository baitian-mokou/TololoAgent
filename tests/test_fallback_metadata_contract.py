import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from src.agent.llm_agent import LLMAgent
from src.vector_store.chroma_store import ChromaStore


ROOT = Path(__file__).resolve().parents[1]
EVAL_SCRIPT_PATH = ROOT / "scripts" / "run_source_expansion_eval.py"


def load_eval_module():
    spec = importlib.util.spec_from_file_location("run_source_expansion_eval", EVAL_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FallbackMetadataContractTests(unittest.TestCase):
    def test_local_json_fallback_adds_schema_version_to_triples_and_narratives(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "火卫一_triples.json").write_text(json.dumps([{
                "subject": "火卫一",
                "relation": "ORBITS",
                "object": "火星",
                "source": "wikidata",
                "source_name": "wikidata",
                "source_role": "primary",
                "origin": "api",
                "source_title": "火卫一"
            }], ensure_ascii=False), encoding="utf-8")
            (temp_path / "火星_narratives.json").write_text(json.dumps([{
                "page_title": "火星",
                "section": "大气",
                "content": "火星大气以二氧化碳为主，并含有少量氮气、氩气和其他微量气体，可用于测试本地 fallback 元数据。",
                "keywords": ["火星", "大气", "成分"],
                "source": "wikidata",
                "source_name": "wikidata",
                "source_role": "primary",
                "origin": "api",
                "source_title": "火星"
            }], ensure_ascii=False), encoding="utf-8")

            agent = LLMAgent(source_name="wikidata")
            agent.triples_dir = str(temp_path)
            agent._entity_catalog = ["火卫一", "火星"]

            triple_results = agent._search_local_triples(
                "火卫一绕谁公转",
                query_context={
                    "query": "火卫一绕谁公转",
                    "primary_entity": "火卫一",
                    "entities": ["火卫一"],
                    "relation_hints": ["ORBITS"],
                    "topic_terms": [],
                },
                source_filter=["wikidata"],
            )
            narrative_results = agent._search_local_narratives(
                "火星大气成分",
                query_context={
                    "query": "火星大气成分",
                    "primary_entity": "火星",
                    "entities": ["火星"],
                    "relation_hints": [],
                    "topic_terms": ["大气", "成分"],
                },
                source_filter=["wikidata"],
            )

        self.assertTrue(triple_results)
        self.assertEqual(triple_results[0]["schema_version"], "wikidata_shadow_ready_v1")
        self.assertTrue(narrative_results)
        self.assertEqual(narrative_results[0]["schema_version"], "wikidata_shadow_ready_v1")

    def test_chroma_metadata_helper_defaults_schema_version(self):
        store = ChromaStore(source_name="nasa")
        metadata = store._extract_source_metadata({"source_name": "nasa", "origin": "api"}, "火星")

        self.assertEqual(metadata["source_name"], "nasa")
        self.assertEqual(metadata["schema_version"], "nasa_shadow_ready_v1")

    def test_source_expansion_eval_rejects_missing_schema_version(self):
        module = load_eval_module()
        self.assertFalse(module.metadata_ok({
            "source": "wikidata",
            "source_name": "wikidata",
            "source_role": "primary",
            "origin": "api",
            "source_title": "火星",
        }, "wikidata", "wikidata_shadow_ready_v1"))

    def test_local_json_fallback_overrides_legacy_schema_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "火卫一_triples.json").write_text(json.dumps([{
                "subject": "火卫一",
                "relation": "ORBITS",
                "object": "火星",
                "source": "zh_wikipedia",
                "source_name": "zh_wikipedia",
                "source_role": "primary",
                "origin": "html_fallback",
                "source_title": "火卫一",
                "schema_version": "2.0"
            }], ensure_ascii=False), encoding="utf-8")

            agent = LLMAgent(source_name="zh_wikipedia")
            agent.triples_dir = str(temp_path)
            results = agent._search_local_triples(
                "火卫一绕谁公转",
                query_context={
                    "query": "火卫一绕谁公转",
                    "primary_entity": "火卫一",
                    "entities": ["火卫一"],
                    "relation_hints": ["ORBITS"],
                    "topic_terms": [],
                },
                source_filter=["zh_wikipedia"],
            )

        self.assertTrue(results)
        self.assertEqual(results[0]["schema_version"], "zh_wikipedia_single_source_v1")


if __name__ == "__main__":
    unittest.main()

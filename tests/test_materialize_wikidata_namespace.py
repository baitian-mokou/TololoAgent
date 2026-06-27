import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "materialize_wikidata_namespace.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_wikidata_namespace", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MaterializeWikidataNamespaceTests(unittest.TestCase):
    def test_materialization_report_reflects_graph_and_embedding_probes(self):
        module = load_module()
        original_argv = sys.argv[:]
        original_base_dir = module.BASE_DIR
        original_triples_dir = module.TRIPLES_DIR
        original_raw_json_dir = module.RAW_JSON_DIR

        class FakeNeo4jLoader:
            def __init__(self, source_name=None):
                self.source_name = source_name

            def load_all_triples(self, triples_dir=None):
                return 2, 1

            def get_stats(self):
                return {"nodes": 2, "rels": 1}

        class FakeChromaStore:
            def __init__(self, source_name=None):
                self.source_name = source_name

            def load_all_narratives(self, narratives_dir=None, replace_existing=False):
                return 1

            def get_stats(self):
                return {"total": 1, "collections": ["astronomy_narratives_wikidata"]}

        class FakeAgent:
            def __init__(self, source_name=None):
                self.source_name = source_name

            def search_neo4j_trace(self, query, limit=20, source_filter=None):
                return {
                    "final_source": "graph",
                    "final_result": [{
                        "subject": "火卫一",
                        "relation": "ORBITS",
                        "object": "火星",
                        "source": "wikidata",
                    }],
                }

            def search_chroma(self, query, top_k=5, source_filter=None):
                return [{
                    "page_title": "火星",
                    "section": "大气",
                    "source": "wikidata",
                    "source_name": "wikidata",
                }]

        module.Neo4jLoader = FakeNeo4jLoader
        module.ChromaStore = FakeChromaStore
        module.LLMAgent = FakeAgent

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                module.BASE_DIR = str(temp_path)
                module.RAW_JSON_DIR = str(temp_path / "raw_json")
                module.TRIPLES_DIR = str(temp_path / "triples")

                fixture_dir = temp_path / "data" / "source_fixtures" / "wikidata"
                fixture_dir.mkdir(parents=True, exist_ok=True)
                (fixture_dir / "solar_system_fixture.json").write_text(json.dumps({
                    "version": "test_fixture",
                    "source_name": "wikidata",
                    "records": [
                        {
                            "title": "火卫一",
                            "triples": [{
                                "subject": "火卫一",
                                "relation": "ORBITS",
                                "object": "火星",
                            }],
                            "narratives": [{
                                "page_title": "火星",
                                "section": "大气",
                                "content": "火星大气以二氧化碳为主。",
                                "keywords": ["火星", "大气"],
                            }],
                        }
                    ],
                }, ensure_ascii=False), encoding="utf-8")

                output_path = temp_path / "wikidata_materialization_report.json"
                sys.argv = [str(SCRIPT_PATH), "--output", str(output_path)]
                with contextlib.redirect_stdout(io.StringIO()):
                    module.main()

                report = json.loads(output_path.read_text(encoding="utf-8"))
        finally:
            sys.argv = original_argv
            module.BASE_DIR = original_base_dir
            module.TRIPLES_DIR = original_triples_dir
            module.RAW_JSON_DIR = original_raw_json_dir

        self.assertEqual(report["source_name"], "wikidata")
        self.assertEqual(report["probes"]["graph_final_source"], "graph")
        self.assertEqual(report["probes"]["narrative_result_count"], 1)
        self.assertEqual(report["chroma"]["stats"]["total"], 1)


if __name__ == "__main__":
    unittest.main()

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_source_expansion_eval.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_source_expansion_eval", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RunSourceExpansionEvalTests(unittest.TestCase):
    def test_empty_queryset_skips_agent_and_chroma_initialization(self):
        module = load_module()
        counts = {"agent": 0, "chroma": 0}

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                counts["agent"] += 1

        class FakeChromaStore:
            def __init__(self, *args, **kwargs):
                counts["chroma"] += 1

            def get_stats(self):
                return {"total": 0}

        fake_vector_store = types.ModuleType("src.vector_store.chroma_store")
        fake_vector_store.ChromaStore = FakeChromaStore
        original_vector_store = sys.modules.get("src.vector_store.chroma_store")
        original_argv = sys.argv[:]
        original_has_store = module.has_materialized_embedding_store
        module.LLMAgent = FakeAgent
        module.has_materialized_embedding_store = lambda source_name: False
        sys.modules["src.vector_store.chroma_store"] = fake_vector_store

        queryset = {
            "version": "source_expansion_gold_set_v1",
            "source_name": "wikidata",
            "source_schema_version": "wikidata_shadow_ready_v1",
            "top_k_default": 5,
            "gates": {
                "exact_accuracy_min": 0.0,
                "source_filter_failure_max": 0,
                "metadata_contract_break_max": 0,
                "inferred_boundary_break_max": 0,
                "query_explainability_degraded_max": 0,
            },
            "queries": [],
        }

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                queryset_path = temp_path / "wikidata_queries.json"
                output_path = temp_path / "wikidata_report.json"
                queryset_path.write_text(json.dumps(queryset, ensure_ascii=False), encoding="utf-8")
                sys.argv = [
                    str(SCRIPT_PATH),
                    "--source",
                    "wikidata",
                    "--queryset",
                    str(queryset_path),
                    "--output",
                    str(output_path),
                ]
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as exit_info:
                        module.main()
                self.assertEqual(exit_info.exception.code, 2)
        finally:
            sys.argv = original_argv
            module.has_materialized_embedding_store = original_has_store
            if original_vector_store is None:
                sys.modules.pop("src.vector_store.chroma_store", None)
            else:
                sys.modules["src.vector_store.chroma_store"] = original_vector_store

        self.assertEqual(counts["agent"], 0)
        self.assertEqual(counts["chroma"], 0)

    def test_narrative_eval_uses_local_fallback_without_searching_chroma_when_store_absent(self):
        module = load_module()
        counts = {"agent": 0, "chroma": 0, "search_chroma": 0}

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                counts["agent"] += 1

            def search_chroma(self, *args, **kwargs):
                counts["search_chroma"] += 1
                return [{
                    "page_title": "火星",
                    "section": "大气",
                    "content": "unexpected",
                    "source": "wikidata",
                    "source_name": "wikidata",
                    "source_role": "primary",
                    "origin": "api",
                    "source_title": "火星",
                    "schema_version": "wikidata_shadow_ready_v1",
                }]

            def _search_local_narratives(self, *args, **kwargs):
                return [{
                    "page_title": "火星",
                    "section": "大气",
                    "content": "local fallback",
                    "score": 1.0,
                    "rank": 1,
                    "source": "wikidata",
                    "source_name": "wikidata",
                    "source_role": "primary",
                    "origin": "api",
                    "source_title": "火星",
                    "schema_version": "wikidata_shadow_ready_v1",
                }]

        class FakeChromaStore:
            def __init__(self, *args, **kwargs):
                counts["chroma"] += 1

            def get_stats(self):
                return {"total": 0}

        fake_vector_store = types.ModuleType("src.vector_store.chroma_store")
        fake_vector_store.ChromaStore = FakeChromaStore
        original_vector_store = sys.modules.get("src.vector_store.chroma_store")
        original_argv = sys.argv[:]
        original_has_store = module.has_materialized_embedding_store
        module.LLMAgent = FakeAgent
        module.has_materialized_embedding_store = lambda source_name: False
        sys.modules["src.vector_store.chroma_store"] = fake_vector_store

        queryset = {
            "version": "source_expansion_gold_set_v1",
            "source_name": "wikidata",
            "source_schema_version": "wikidata_shadow_ready_v1",
            "top_k_default": 5,
            "gates": {
                "exact_accuracy_min": 0.0,
                "source_filter_failure_max": 0,
                "metadata_contract_break_max": 0,
                "inferred_boundary_break_max": 0,
                "query_explainability_degraded_max": 0,
            },
            "queries": [
                {
                    "id": "wikidata_narrative_mars_atmosphere",
                    "category": "narrative",
                    "query_kind": "narrative",
                    "query": "火星大气成分",
                    "expected_path": "fallback",
                    "allowed_final_sources": ["fallback"],
                    "expected_top_k_hit": True,
                    "expected_page_title": "火星",
                    "expected_section_any_of": ["大气"],
                    "expected_result": {
                        "page_title": "火星",
                        "section_any_of": ["大气"],
                    },
                    "source_filter": ["wikidata"],
                    "source_schema_version": "wikidata_shadow_ready_v1",
                }
            ],
        }

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                queryset_path = temp_path / "wikidata_queries.json"
                output_path = temp_path / "wikidata_report.json"
                queryset_path.write_text(json.dumps(queryset, ensure_ascii=False), encoding="utf-8")
                sys.argv = [
                    str(SCRIPT_PATH),
                    "--source",
                    "wikidata",
                    "--queryset",
                    str(queryset_path),
                    "--output",
                    str(output_path),
                ]
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as exit_info:
                        module.main()
                self.assertEqual(exit_info.exception.code, 2)
        finally:
            sys.argv = original_argv
            module.has_materialized_embedding_store = original_has_store
            if original_vector_store is None:
                sys.modules.pop("src.vector_store.chroma_store", None)
            else:
                sys.modules["src.vector_store.chroma_store"] = original_vector_store

        self.assertEqual(counts["agent"], 1)
        self.assertEqual(counts["chroma"], 0)
        self.assertEqual(counts["search_chroma"], 0)

    def test_owner_override_manifest_can_force_local_fallback_paths(self):
        module = load_module()
        counts = {"graph": 0, "chroma": 0}

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                pass

            def search_neo4j_trace(self, *args, **kwargs):
                counts["graph"] += 1
                return {
                    "graph_only": [],
                    "final_result": [{
                        "subject": "火卫一",
                        "relation": "ORBITS",
                        "object": "火星",
                        "source": "wikidata",
                        "source_name": "wikidata",
                        "source_role": "primary",
                        "origin": "api",
                        "source_title": "火卫一",
                        "schema_version": "wikidata_shadow_ready_v1",
                    }],
                    "final_source": "graph",
                }

            def search_chroma(self, *args, **kwargs):
                counts["chroma"] += 1
                return [{
                    "page_title": "火星",
                    "section": "大气",
                    "content": "unexpected live path",
                    "score": 1.0,
                    "rank": 1,
                    "source": "wikidata",
                    "source_name": "wikidata",
                    "source_role": "primary",
                    "origin": "api",
                    "source_title": "火星",
                    "schema_version": "wikidata_shadow_ready_v1",
                }]

            def _search_local_triples(self, *args, **kwargs):
                return [{
                    "subject": "火卫一",
                    "relation": "ORBITS",
                    "object": "火星",
                    "source": "wikidata",
                    "source_name": "wikidata",
                    "source_role": "primary",
                    "origin": "api",
                    "source_title": "火卫一",
                    "schema_version": "wikidata_shadow_ready_v1",
                }]

            def _search_local_narratives(self, *args, **kwargs):
                return [{
                    "page_title": "火星",
                    "section": "大气",
                    "content": "local fallback",
                    "score": 1.0,
                    "rank": 1,
                    "source": "wikidata",
                    "source_name": "wikidata",
                    "source_role": "primary",
                    "origin": "api",
                    "source_title": "火星",
                    "schema_version": "wikidata_shadow_ready_v1",
                }]

        original_argv = sys.argv[:]
        module.LLMAgent = FakeAgent

        queryset = {
            "version": "source_expansion_gold_set_v1",
            "source_name": "wikidata",
            "source_schema_version": "wikidata_shadow_ready_v1",
            "top_k_default": 5,
            "force_local_graph_fallback": True,
            "force_local_narrative_fallback": True,
            "gates": {
                "exact_accuracy_min": 1.0,
                "source_filter_failure_max": 0,
                "metadata_contract_break_max": 0,
                "inferred_boundary_break_max": 0,
                "query_explainability_degraded_max": 0,
            },
            "queries": [
                {
                    "id": "wikidata_structured_orbit",
                    "category": "structured",
                    "query_kind": "structured",
                    "query": "火卫一绕谁公转",
                    "expected_path": "fallback",
                    "allowed_final_sources": ["fallback"],
                    "expected_top_k_hit": True,
                    "expected_result": {
                        "subject": "火卫一",
                        "relation": "ORBITS",
                        "object": "火星",
                    },
                    "source_filter": ["wikidata"],
                    "source_schema_version": "wikidata_shadow_ready_v1",
                },
                {
                    "id": "wikidata_narrative_mars_atmosphere",
                    "category": "narrative",
                    "query_kind": "narrative",
                    "query": "火星大气成分",
                    "expected_path": "fallback",
                    "allowed_final_sources": ["fallback"],
                    "expected_top_k_hit": True,
                    "expected_page_title": "火星",
                    "expected_section_any_of": ["大气"],
                    "expected_result": {
                        "page_title": "火星",
                        "section_any_of": ["大气"],
                    },
                    "source_filter": ["wikidata"],
                    "source_schema_version": "wikidata_shadow_ready_v1",
                },
            ],
        }

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                queryset_path = temp_path / "wikidata_queries.json"
                output_path = temp_path / "wikidata_report.json"
                queryset_path.write_text(json.dumps(queryset, ensure_ascii=False), encoding="utf-8")
                sys.argv = [
                    str(SCRIPT_PATH),
                    "--source",
                    "wikidata",
                    "--queryset",
                    str(queryset_path),
                    "--output",
                    str(output_path),
                ]
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as exit_info:
                        module.main()
                self.assertEqual(exit_info.exception.code, 2)
        finally:
            sys.argv = original_argv

        self.assertEqual(counts["graph"], 0)
        self.assertEqual(counts["chroma"], 0)

    def test_search_chroma_does_not_create_disabled_namespace_when_store_is_not_materialized(self):
        from src.agent.llm_agent import LLMAgent

        chroma_dir = ROOT / "data" / "chroma_db" / "esa"
        if chroma_dir.exists():
            shutil.rmtree(chroma_dir)

        agent = LLMAgent(source_name="esa")
        calls = {"local": 0}

        def fake_local_search(query, top_k=5, query_context=None, source_filter=None):
            calls["local"] += 1
            return [{
                "page_title": "火星",
                "section": "大气",
                "content": "local fallback",
                "score": 1.0,
                "rank": 1,
                "source": "esa",
                "source_name": "esa",
                "source_role": "primary",
                "origin": "api",
                "source_title": "火星",
                "schema_version": "esa_shadow_ready_v1",
            }]

        original_local = agent._search_local_narratives
        agent._search_local_narratives = fake_local_search
        try:
            results = agent.search_chroma("火星大气成分", source_filter=["esa"])
        finally:
            agent._search_local_narratives = original_local
            if chroma_dir.exists():
                shutil.rmtree(chroma_dir)

        self.assertEqual(calls["local"], 1)
        self.assertFalse(chroma_dir.exists())
        self.assertEqual(results[0]["source_name"], "esa")


if __name__ == "__main__":
    unittest.main()

import json
import os
import unittest

from src.agent.llm_agent import LLMAgent
from src.nlp.query_analyzer import build_query_context
from src.vector_store.chroma_store import ChromaStore


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUN_NARRATIVES = os.path.join(ROOT, "data", "triples", "太阳_narratives.json")
EXPECTED_SECTIONS = {"概要", "核心", "核心 (2)"}


def load_sun_section(section_name):
    with open(SUN_NARRATIVES, "r", encoding="utf-8") as handle:
        records = json.load(handle)
    for record in records:
        if record.get("section") == section_name:
            return record
    raise AssertionError(f"Missing section {section_name}")


class NarrativeRankingRegressionTests(unittest.TestCase):
    def test_solar_luminosity_query_context_has_domain_hints(self):
        context = build_query_context("为什么太阳会发光", known_titles=["太阳"])

        self.assertIn("solar_luminosity", context["topic_intents"])
        self.assertNotIn("为什么", context["topic_terms"])
        self.assertIn("核融合", context["topic_terms"])
        self.assertIn("能量来源", context["topic_terms"])

    def test_narrative_sun_shines_local_top1_hits_expected_section(self):
        agent = LLMAgent()

        results = agent._search_local_narratives("为什么太阳会发光", top_k=5)

        self.assertTrue(results)
        self.assertEqual(results[0]["page_title"], "太阳")
        self.assertIn(results[0]["section"], EXPECTED_SECTIONS)

    def test_solar_luminosity_rerank_prefers_fusion_context_over_radiative_layer(self):
        store = object.__new__(ChromaStore)
        context = build_query_context("为什么太阳会发光", known_titles=["太阳"])

        core = load_sun_section("核心")
        radiative = load_sun_section("辐射层")
        core_score = store._score_narrative_candidate(core, context, vector_score=0.0)
        radiative_score = store._score_narrative_candidate(radiative, context, vector_score=0.0)

        self.assertGreater(core_score, radiative_score)


if __name__ == "__main__":
    unittest.main()

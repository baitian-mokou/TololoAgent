import unittest

from src.agent.llm_agent import LLMAgent
from src.nlp.query_analyzer import build_query_context


REQUIRED_METADATA = ("source", "source_name", "source_role", "origin", "schema_version", "source_title")


class SourceExpansionFailureRepairTests(unittest.TestCase):
    def test_wikidata_pluto_belongs_query_prefers_part_of(self):
        agent = LLMAgent(source_name="wikidata")
        results = agent._search_local_triples("冥王星属于哪里", limit=3, source_filter=["wikidata"])

        self.assertTrue(results)
        self.assertEqual(results[0]["subject"], "冥王星")
        self.assertEqual(results[0]["relation"], "PART_OF")
        self.assertEqual(results[0]["object"], "柯伊伯带")
        self.assertTrue(all(results[0].get(field) for field in REQUIRED_METADATA))

    def test_wikidata_mars_mass_keeps_e_notation(self):
        agent = LLMAgent(source_name="wikidata")
        results = agent._search_local_triples("火星质量是多少", limit=3, source_filter=["wikidata"])

        self.assertTrue(results)
        self.assertEqual(results[0]["subject"], "火星")
        self.assertEqual(results[0]["relation"], "HAS_MASS")
        self.assertEqual(results[0]["object"], "6.4171e23 kg")
        self.assertTrue(all(results[0].get(field) for field in REQUIRED_METADATA))

    def test_wikidata_mars_mass_short_query_keeps_e_notation(self):
        agent = LLMAgent(source_name="wikidata")
        results = agent._search_local_triples("火星的质量", limit=3, source_filter=["wikidata"])

        self.assertTrue(results)
        self.assertEqual(results[0]["subject"], "火星")
        self.assertEqual(results[0]["relation"], "HAS_MASS")
        self.assertEqual(results[0]["object"], "6.4171e23 kg")
        self.assertTrue(all(results[0].get(field) for field in REQUIRED_METADATA))

    def test_wikidata_nonexistent_satellite_query_returns_empty(self):
        agent = LLMAgent(source_name="wikidata")
        results = agent._search_local_triples(
            "Wikidata 不存在的火星第三颗卫星绕谁运行",
            limit=3,
            source_filter=["wikidata"],
        )

        self.assertEqual(results, [])

    def test_nasa_deimos_query_hits_deimos_not_phobos(self):
        agent = LLMAgent(source_name="nasa")
        results = agent._search_local_triples("火卫二绕谁公转", limit=3, source_filter=["nasa"])

        self.assertTrue(results)
        self.assertEqual(results[0]["subject"], "火卫二")
        self.assertEqual(results[0]["relation"], "ORBITS")
        self.assertEqual(results[0]["object"], "火星")
        self.assertNotEqual(results[0]["subject"], "火卫一")

    def test_wikidata_earth_located_in_query_returns_solar_system(self):
        agent = LLMAgent(source_name="wikidata")
        results = agent._search_local_triples("地球位于哪里", limit=3, source_filter=["wikidata"])

        self.assertTrue(results)
        self.assertEqual(results[0]["subject"], "地球")
        self.assertEqual(results[0]["relation"], "LOCATED_IN")
        self.assertEqual(results[0]["object"], "太阳系")
        self.assertTrue(all(results[0].get(field) for field in REQUIRED_METADATA))

    def test_wikidata_moon_located_in_query_returns_earth_system(self):
        agent = LLMAgent(source_name="wikidata")
        results = agent._search_local_triples("月球位于哪里", limit=3, source_filter=["wikidata"])

        self.assertTrue(results)
        self.assertEqual(results[0]["subject"], "月球")
        self.assertEqual(results[0]["relation"], "LOCATED_IN")
        self.assertEqual(results[0]["object"], "地球系统")
        self.assertTrue(all(results[0].get(field) for field in REQUIRED_METADATA))

    def test_nasa_mars_mass_query_returns_shadow_fact(self):
        agent = LLMAgent(source_name="nasa")
        results = agent._search_local_triples("火星质量是多少", limit=3, source_filter=["nasa"])

        self.assertTrue(results)
        self.assertEqual(results[0]["subject"], "火星")
        self.assertEqual(results[0]["relation"], "HAS_MASS")
        self.assertEqual(results[0]["object"], "6.4171e23 kg")
        self.assertTrue(all(results[0].get(field) for field in REQUIRED_METADATA))

    def test_nasa_earth_atmosphere_query_does_not_match_mars_fixture(self):
        agent = LLMAgent(source_name="nasa")
        results = agent._search_local_narratives("地球大气成分", top_k=3, source_filter=["nasa"])

        self.assertTrue(results)
        self.assertEqual(results[0]["page_title"], "地球")
        self.assertTrue(all(results[0].get(field) for field in REQUIRED_METADATA))

    def test_non_active_source_filter_skips_graph_path(self):
        agent = LLMAgent()

        class FakeLoader:
            driver = object()

            def search_graph(self, query_context, limit=20, source_filter=None):
                return [{
                    "subject": "海王星",
                    "relation": "LOCATED_IN",
                    "object": "太阳系",
                    "source": "wikidata",
                    "source_name": "wikidata",
                    "source_role": "primary",
                    "origin": "api",
                    "source_title": "海王星",
                    "schema_version": "wikidata_shadow_ready_v1",
                }]

        agent._neo4j_loader = FakeLoader()
        trace = agent.search_neo4j_trace("海王星在哪里", limit=3, source_filter=["wikidata"])

        self.assertEqual(trace["final_source"], "fallback")
        self.assertEqual(trace["graph_only"], [])
        self.assertEqual(trace["final_result"], [])

    def test_esa_venus_express_orbits_venus(self):
        agent = LLMAgent(source_name="esa")
        results = agent._search_local_triples("金星快车号绕谁运行", limit=3, source_filter=["esa"])

        self.assertTrue(results)
        self.assertEqual(results[0]["subject"], "金星快车号")
        self.assertEqual(results[0]["relation"], "ORBITS")
        self.assertEqual(results[0]["object"], "金星")
        self.assertTrue(all(results[0].get(field) for field in REQUIRED_METADATA))

    def test_query_analyzer_marks_source_isolation_entities(self):
        context = build_query_context("地球大气成分", known_titles=["火星"])

        self.assertEqual(context["primary_entity"], "地球")
        self.assertIn("HAS_ATMOSPHERE", context["relation_hints"])


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

from src.agent.llm_agent import LLMAgent


class SourceAuthorityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.agent = LLMAgent(source_name="auto")

    def test_has_radius_prefers_nasa(self):
        fused = self.agent._fuse_auto_results(
            "火星半径是多少",
            neo4j_by_source={
                "nasa": [{
                    "subject": "火星",
                    "relation": "HAS_RADIUS",
                    "object": "3389.5 km",
                    "source": "nasa",
                    "source_name": "nasa",
                }],
                "wikidata": [{
                    "subject": "火星",
                    "relation": "HAS_RADIUS",
                    "object": "3396.2 km",
                    "source": "wikidata",
                    "source_name": "wikidata",
                }],
                "zh_wikipedia": [{
                    "subject": "火星",
                    "relation": "HAS_RADIUS",
                    "object": "3390 km",
                    "source": "zh_wikipedia",
                    "source_name": "zh_wikipedia",
                }],
            },
            chroma_by_source={},
            routing_trace={
                "intent": "numeric_fact",
                "selected_sources": ["nasa", "wikidata", "zh_wikipedia", "esa"],
                "routing_reason": "numeric peer source routing",
                "fusion_mode": "peer_source_fusion",
            },
        )

        self.assertEqual(fused["metadata"]["authority_by_relation"]["HAS_RADIUS"], "nasa")
        self.assertEqual(fused["metadata"]["authority_source"], "nasa")
        self.assertEqual(fused["neo4j_results"][0]["source_name"], "nasa")

    def test_orbits_prefers_wikidata(self):
        fused = self.agent._fuse_auto_results(
            "月球绕行什么",
            neo4j_by_source={
                "wikidata": [{
                    "subject": "月球",
                    "relation": "ORBITS",
                    "object": "地球",
                    "source": "wikidata",
                    "source_name": "wikidata",
                }],
                "nasa": [{
                    "subject": "月球",
                    "relation": "ORBITS",
                    "object": "地球",
                    "source": "nasa",
                    "source_name": "nasa",
                }],
                "zh_wikipedia": [{
                    "subject": "月球",
                    "relation": "ORBITS",
                    "object": "地球",
                    "source": "zh_wikipedia",
                    "source_name": "zh_wikipedia",
                }],
            },
            chroma_by_source={},
            routing_trace={
                "intent": "structured_fact",
                "selected_sources": ["wikidata", "nasa", "zh_wikipedia", "esa"],
                "routing_reason": "structured peer source routing",
                "fusion_mode": "peer_source_fusion",
            },
        )

        self.assertEqual(fused["metadata"]["authority_by_relation"]["ORBITS"], "wikidata")
        self.assertEqual(fused["neo4j_results"][0]["source_name"], "wikidata")
        self.assertEqual(set(fused["neo4j_results"][0]["merged_sources"]), {"wikidata", "nasa", "zh_wikipedia"})

    def test_esa_mission_prefers_esa(self):
        fused = self.agent._fuse_auto_results(
            "JUICE 探测任务研究什么",
            neo4j_by_source={},
            chroma_by_source={
                "esa": [{"content": "ESA mission", "page_title": "JUICE", "section": "概述", "source": "esa", "source_name": "esa"}],
                "nasa": [{"content": "NASA summary", "page_title": "JUICE", "section": "概述", "source": "nasa", "source_name": "nasa"}],
                "wikidata": [{"content": "Wikidata summary", "page_title": "JUICE", "section": "概述", "source": "wikidata", "source_name": "wikidata"}],
                "zh_wikipedia": [{"content": "zhwiki summary", "page_title": "JUICE", "section": "概述", "source": "zh_wikipedia", "source_name": "zh_wikipedia"}],
            },
            routing_trace={
                "intent": "esa_mission",
                "selected_sources": ["esa", "nasa", "wikidata", "zh_wikipedia"],
                "routing_reason": "esa mission peer source routing",
                "fusion_mode": "peer_source_fusion",
            },
        )

        self.assertEqual(fused["metadata"]["authority_source"], "esa")
        self.assertEqual(fused["chroma_results"][0]["source_name"], "esa")

    def test_why_query_prefers_zh_wikipedia(self):
        fused = self.agent._fuse_auto_results(
            "太阳为什么会发光",
            neo4j_by_source={},
            chroma_by_source={
                "zh_wikipedia": [{"content": "zhwiki explain", "page_title": "太阳", "section": "核心", "source": "zh_wikipedia", "source_name": "zh_wikipedia"}],
                "nasa": [{"content": "nasa explain", "page_title": "太阳", "section": "core", "source": "nasa", "source_name": "nasa"}],
                "esa": [{"content": "esa explain", "page_title": "太阳", "section": "overview", "source": "esa", "source_name": "esa"}],
                "wikidata": [{"content": "wikidata explain", "page_title": "太阳", "section": "概述", "source": "wikidata", "source_name": "wikidata"}],
            },
            routing_trace={
                "intent": "narrative_explanation",
                "selected_sources": ["zh_wikipedia", "nasa", "esa", "wikidata"],
                "routing_reason": "narrative peer source routing",
                "fusion_mode": "peer_source_fusion",
            },
        )

        self.assertEqual(fused["metadata"]["authority_source"], "zh_wikipedia")
        self.assertEqual(fused["chroma_results"][0]["source_name"], "zh_wikipedia")

    def test_manual_single_source_still_bypasses_fusion_policy(self):
        agent = LLMAgent(source_name="wikidata")
        with patch.object(agent, "search_neo4j", return_value=[]), patch.object(
            agent, "search_chroma", return_value=[]
        ), patch.object(agent, "chat", return_value="manual source answer"):
            result = agent.ask("月球绕行什么")

        self.assertEqual(result["metadata"]["fusion_mode"], "single_source")
        self.assertFalse(result["metadata"]["authority_policy_applied"])
        self.assertEqual(result["metadata"]["selected_sources"], ["wikidata"])


if __name__ == "__main__":
    unittest.main()

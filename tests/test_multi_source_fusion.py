import unittest
from unittest.mock import patch

from src.agent.llm_agent import LLMAgent


class MultiSourceFusionTests(unittest.TestCase):
    def test_auto_mode_queries_multiple_sources_and_returns_trace(self):
        agent = LLMAgent(source_name="auto")
        graph_calls = []
        chroma_calls = []

        def fake_graph(query, limit=20, source_filter=None):
            graph_calls.append(tuple(source_filter or ()))
            source_name = (source_filter or ["zh_wikipedia"])[0]
            return [{
                "subject": "火星",
                "relation": "HAS_MASS",
                "object": "6.4171e23 kg",
                "source": source_name,
                "source_name": source_name,
            }]

        def fake_chroma(query, top_k=5, source_filter=None):
            chroma_calls.append(tuple(source_filter or ()))
            source_name = (source_filter or ["zh_wikipedia"])[0]
            return [{
                "content": f"{source_name} 对火星质量的说明",
                "page_title": "火星",
                "section": "概述",
                "source": source_name,
                "source_name": source_name,
            }]

        with patch.object(LLMAgent, "search_neo4j", side_effect=fake_graph), patch.object(
            LLMAgent, "search_chroma", side_effect=fake_chroma
        ), patch.object(agent, "chat", return_value="火星质量约为 6.4171e23 kg。"):
            result = agent.ask("火星质量是多少")

        self.assertIn(("nasa",), graph_calls)
        self.assertIn(("wikidata",), graph_calls)
        self.assertIn(("nasa",), chroma_calls)
        self.assertIn("metadata", result)
        self.assertEqual(result["metadata"]["selected_sources"][0], "nasa")
        self.assertIn("source_trace", result["metadata"])
        self.assertEqual(result["metadata"]["source_result_counts"]["nasa"]["neo4j"], 1)

    def test_auto_fusion_preserves_provenance_and_conflict_signal(self):
        agent = LLMAgent(source_name="auto")

        fused = agent._fuse_auto_results(
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
            },
            chroma_by_source={
                "zh_wikipedia": [{
                    "content": "火星是太阳系的一颗类地行星。",
                    "page_title": "火星",
                    "section": "概述",
                    "source": "zh_wikipedia",
                    "source_name": "zh_wikipedia",
                }]
            },
            routing_trace={
                "selected_sources": ["zh_wikipedia", "wikidata", "nasa"],
                "routing_reason": "mixed_query",
                "fusion_mode": "multi_source_fusion",
            },
        )

        self.assertTrue(fused["metadata"]["conflict_detected"])
        self.assertEqual(
            {item["source_name"] for item in fused["neo4j_results"]},
            {"nasa", "wikidata"},
        )
        self.assertIn("来源存在差异", fused["answer_prompt"])
        self.assertEqual(fused["metadata"]["fusion_mode"], "multi_source_fusion")


if __name__ == "__main__":
    unittest.main()

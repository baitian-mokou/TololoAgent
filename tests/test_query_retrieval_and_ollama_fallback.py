import unittest
from unittest.mock import patch

from src.agent.llm_agent import LLMAgent
from src.nlp.query_analyzer import build_query_context


class _FakeResponse:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read(self, _size=-1):
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class QueryRetrievalAndOllamaFallbackTests(unittest.TestCase):
    def test_query_context_handles_composite_jupiter_question(self):
        context = build_query_context(
            "木星卫星和它自己的参数",
            known_titles=["木星的卫星", "木星"],
            alias_map={"moon": "月球"},
        )

        self.assertIn("木星的卫星", context["entities"])
        self.assertIn("木星", context["entities"])
        self.assertIn("卫星", context["topic_terms"])
        self.assertIn("参数", context["topic_terms"])

    def test_local_retrieval_returns_satellite_and_self_parameters(self):
        agent = LLMAgent()

        narrative_results = agent._search_local_narratives("木星卫星和它自己的参数", top_k=6)
        titles = {item["page_title"] for item in narrative_results}
        self.assertIn("木星的卫星", titles)
        self.assertIn("木星", titles)

        triple_results = agent._search_local_triples("木星卫星和它自己的参数", limit=10)
        self.assertTrue(
            any(item["subject"] == "木星" and item["relation"] in {"HAS_RADIUS", "HAS_MASS"} for item in triple_results),
            triple_results,
        )

    def test_orbit_host_mass_question_resolves_parent_parameter(self):
        agent = LLMAgent()
        query = "火卫一绕行的行星质量是多少"
        context = build_query_context(query)

        results = agent._resolve_orbit_host_parameter(
            context,
            [{"subject": "火卫一", "relation": "ORBITS", "object": "火星", "source": "zh_wikipedia"}],
            loader=None,
            limit=5,
            source_filter=["zh_wikipedia"],
        )

        self.assertEqual(results[0]["subject"], "火星")
        self.assertEqual(results[0]["relation"], "HAS_MASS")
        self.assertEqual(results[0]["object"], "6.4169 × 10 23 kg")

    def test_orbit_host_type_question_resolves_parent_type(self):
        agent = LLMAgent()
        query = "火卫一绕行的天体在数据集中被标注为什么特殊类型？"
        context = build_query_context(query)

        results = agent._resolve_multi_hop_query(
            context,
            [{"subject": "火卫一", "relation": "ORBITS", "object": "火星", "source": "zh_wikipedia"}],
            loader=None,
            limit=5,
            source_filter=["zh_wikipedia"],
        )

        self.assertEqual(results[0]["subject"], "火星")
        self.assertEqual(results[0]["relation"], "IS_A")
        self.assertEqual(results[0]["object"], "沙漠行星")

    def test_orbit_host_atmosphere_accepts_celestial_body_wording(self):
        agent = LLMAgent()
        query = "冥卫一绕行的天体大气成分有哪些？"
        context = build_query_context(query)

        results = agent._resolve_multi_hop_query(
            context,
            [{"subject": "冥卫一", "relation": "ORBITS", "object": "冥王星", "source": "zh_wikipedia"}],
            loader=None,
            limit=10,
            source_filter=["zh_wikipedia"],
        )

        objects = {item["object"] for item in results}
        self.assertIn("氮", objects)
        self.assertIn("甲烷", objects)
        self.assertIn("一氧化碳", objects)

    def test_named_group_relation_resolves_second_hop(self):
        agent = LLMAgent()
        query = "木卫二所属的伽利略卫星是什么类型？"
        context = build_query_context(query)

        results = agent._resolve_multi_hop_query(
            context,
            [],
            loader=None,
            limit=5,
            source_filter=["zh_wikipedia"],
        )

        self.assertEqual(results[0]["subject"], "伽利略卫星")
        self.assertEqual(results[0]["relation"], "IS_A")
        self.assertEqual(results[0]["object"], "天然卫星群")

    def test_reverse_discoverer_and_system_filter(self):
        agent = LLMAgent()
        query = "哪些属于土星系统的卫星由乔瓦尼·多梅尼科·卡西尼发现？"
        context = build_query_context(query)

        results = agent._resolve_multi_hop_query(
            context,
            [],
            loader=None,
            limit=10,
            source_filter=["zh_wikipedia"],
        )

        subjects = {item["subject"] for item in results}
        self.assertTrue({"土卫四", "土卫五", "土卫八"}.issubset(subjects), results)

    def test_reverse_discoverer_then_orbit_relation(self):
        agent = LLMAgent()
        query = "威廉·赫歇尔发现的土星卫星绕谁公转？"
        context = build_query_context(query)

        results = agent._resolve_multi_hop_query(
            context,
            [],
            loader=None,
            limit=5,
            source_filter=["zh_wikipedia"],
        )

        self.assertEqual(results[0]["subject"], "土卫一")
        self.assertEqual(results[0]["relation"], "ORBITS")
        self.assertEqual(results[0]["object"], "土星")

    def test_reverse_orbits_sun_and_type_filter(self):
        agent = LLMAgent()
        query = "哪个绕太阳公转的实体在数据集中被标注为类地行星？"
        context = build_query_context(query)

        results = agent._resolve_multi_hop_query(
            context,
            [],
            loader=None,
            limit=5,
            source_filter=["zh_wikipedia"],
        )

        self.assertEqual(results[0]["subject"], "金星")
        self.assertEqual(results[0]["relation"], "IS_A")
        self.assertEqual(results[0]["object"], "类地行星")

    def test_moon_host_diameter_question_derives_earth_diameter(self):
        agent = LLMAgent()
        query = "月亮的行星的直径"
        context = agent._extract_query_context(query)

        self.assertEqual(context["primary_entity"], "月球")
        self.assertIn("ORBITS", context["relation_hints"])
        self.assertIn("HAS_RADIUS", context["relation_hints"])
        self.assertIn("diameter", context["topic_intents"])

        results = agent._resolve_multi_hop_query(
            context,
            [{"subject": "月球", "relation": "ORBITS", "object": "地球", "source": "zh_wikipedia"}],
            loader=None,
            limit=5,
            source_filter=["zh_wikipedia"],
        )

        self.assertEqual(results[0]["subject"], "地球")
        self.assertEqual(results[0]["relation"], "HAS_DIAMETER")
        self.assertIn("12,742.0 km", results[0]["object"])
        self.assertIn("由半径", results[0]["object"])

    def test_moon_host_diameter_and_mass_question_keeps_both_parameters(self):
        agent = LLMAgent()
        query = "月亮所属行星的直径与质量"
        context = agent._extract_query_context(query)

        self.assertEqual(context["primary_entity"], "月球")
        self.assertIn("ORBITS", context["relation_hints"])
        self.assertIn("HAS_RADIUS", context["relation_hints"])
        self.assertIn("HAS_MASS", context["relation_hints"])

        results = agent._resolve_multi_hop_query(
            context,
            [{"subject": "月球", "relation": "ORBITS", "object": "地球", "source": "zh_wikipedia"}],
            loader=None,
            limit=5,
            source_filter=["zh_wikipedia"],
        )

        facts = {(item["subject"], item["relation"]) for item in results}
        self.assertIn(("地球", "HAS_DIAMETER"), facts)
        self.assertIn(("地球", "HAS_MASS"), facts)
        self.assertTrue(any("12,742.0 km" in item["object"] for item in results), results)
        self.assertTrue(any(item["object"].startswith("5.972") for item in results), results)

    def test_ollama_stream_empty_falls_back_to_non_stream(self):
        agent = LLMAgent()
        streamed_lines = (
            b'{"model":"qwen3:4b","message":{"role":"assistant","content":"","thinking":"Okay"},"done":false}\n',
            b'{"model":"qwen3:4b","message":{"role":"assistant","content":"","thinking":"done"},"done":true}\n',
            b'',
        )
        non_stream_body = '{"model":"qwen3:4b","message":{"role":"assistant","content":"最终答案"},"done":true}'.encode("utf-8")

        with patch("urllib.request.urlopen", side_effect=[_FakeResponse(streamed_lines), _FakeResponse([non_stream_body])]):
            answer = agent._call_ollama([{"role": "user", "content": "hi"}], on_token=lambda token: None)

        self.assertEqual(answer, "最终答案")

    def test_model_available_accepts_ollama_model_field(self):
        agent = LLMAgent()
        tags_body = b'{"models":[{"model":"qwen3:4b","name":""}]}'

        with patch("urllib.request.urlopen", return_value=_FakeResponse([tags_body])):
            self.assertTrue(agent.is_model_available())

    def test_model_available_falls_back_to_show_probe(self):
        agent = LLMAgent()
        tags_body = b'{"models":[]}'
        show_body = b'{"modelfile":"FROM qwen3:4b"}'

        with patch("urllib.request.urlopen", side_effect=[_FakeResponse([tags_body]), _FakeResponse([show_body])]):
            self.assertTrue(agent.is_model_available())

    def test_remote_api_uses_remote_model_not_ollama_model(self):
        agent = LLMAgent()
        agent.api_base = "https://api.deepseek.com"
        agent.api_key = "test-key"
        agent.model = "qwen3:4b"
        agent.remote_model = "deepseek-v4-flash"
        response_body = b'{"choices":[{"message":{"content":"ok"}}]}'

        def fake_urlopen(req, timeout=None):
            payload = req.data.decode("utf-8")
            self.assertIn('"model": "deepseek-v4-flash"', payload)
            self.assertNotIn('"model": "qwen3:4b"', payload)
            return _FakeResponse([response_body])

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self.assertEqual(agent._call_remote_api([{"role": "user", "content": "hi"}]), "ok")

    def test_extract_answer_from_thinking_when_content_is_empty(self):
        agent = LLMAgent()
        data = {
            "message": {
                "content": "",
                "thinking": "分析过程... 最终回答：木星半径69886.0 km，质量1.8981 × 10 27 kg。",
            }
        }

        answer = agent._extract_usable_ollama_content(data)
        self.assertEqual(answer, "木星半径69886.0 km，质量1.8981 × 10 27 kg。")

    def test_sanitize_final_answer_strips_meta_reasoning(self):
        agent = LLMAgent()
        raw = "木星半径69886.0千米。\n\n检查是否引用检索：\n- 这里不该保留"
        cleaned = agent._sanitize_final_answer(raw)
        self.assertEqual(cleaned, "木星半径69886.0千米。")


if __name__ == "__main__":
    unittest.main()

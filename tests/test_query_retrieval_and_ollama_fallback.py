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

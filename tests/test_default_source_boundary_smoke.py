import json
import os
import tempfile
import unittest

from scripts import smoke_default_source_boundary as smoke


class FakeLLMAgent:
    def __init__(self):
        self.calls = []

    def search_neo4j_trace(self, query, limit=5, source_filter=None):
        self.calls.append(("graph", query, tuple(source_filter or [])))
        if source_filter:
            return {"final_source": "fallback", "final_result": []}
        return {
            "final_source": "fallback",
            "final_result": [
                {
                    "subject": "火卫一",
                    "relation": "ORBITS",
                    "object": "火星",
                    "source": "zh_wikipedia",
                    "source_name": "zh_wikipedia",
                    "source_role": "primary",
                    "origin": "html_fallback",
                    "schema_version": "zh_wikipedia_single_source_v1",
                    "source_title": "火卫一",
                }
            ],
        }

    def search_chroma(self, query, top_k=5, source_filter=None):
        self.calls.append(("chroma", query, tuple(source_filter or [])))
        if source_filter:
            return []
        return [
            {
                "content": "火星大气以二氧化碳为主。",
                "page_title": "火星",
                "section": "大气",
                "source": "zh_wikipedia",
                "source_name": "zh_wikipedia",
                "source_role": "primary",
                "origin": "html_fallback",
                "schema_version": "zh_wikipedia_single_source_v1",
                "source_title": "火星",
            }
        ]


class DefaultSourceBoundarySmokeTests(unittest.TestCase):
    def test_source_registry_boundary_keeps_shadow_sources_disabled(self):
        checks = smoke.assert_source_registry_boundary()
        self.assertTrue(all(item["passed"] for item in checks))
        self.assertEqual(checks[0]["actual"], "zh_wikipedia")

    def test_settings_hygiene_allows_env_placeholder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "settings.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"llm_source": {"api_key": "${TOLOLO_REMOTE_API_KEY}"}}, handle)

            check = smoke.check_settings_key_hygiene(path)

        self.assertTrue(check["passed"])

    def test_settings_hygiene_rejects_literal_sk_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "settings.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"llm_source": {"api_key": "s" + "k-" + "dummysecretvalue"}}, handle)

            check = smoke.check_settings_key_hygiene(path)

        self.assertFalse(check["passed"])

    def test_report_shape_with_mocked_agent(self):
        report, exit_code = smoke.run_smoke(
            agent_factory=FakeLLMAgent,
            settings_path=os.path.join(os.path.dirname(__file__), "missing_settings.json"),
            write_report=False,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["passed"])
        self.assertIn("source_registry", report["checks"])
        self.assertIn("default_queries", report["checks"])
        self.assertIn("explicit_filter_isolation", report["checks"])
        self.assertIn("settings_key_hygiene", report["checks"])
        self.assertEqual(len(report["checks"]["default_queries"]), 2)
        self.assertEqual(len(report["checks"]["explicit_filter_isolation"]), 6)


if __name__ == "__main__":
    unittest.main()

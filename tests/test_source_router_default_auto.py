import unittest

from src.source_router import SourceRouter


class SourceRouterDefaultAutoTests(unittest.TestCase):
    def setUp(self):
        self.router = SourceRouter()

    def test_numeric_query_prefers_nasa_and_wikidata(self):
        trace = self.router.route("火星质量是多少")

        self.assertEqual(trace["selected_sources"][0], "nasa")
        self.assertIn("wikidata", trace["selected_sources"])
        self.assertEqual(trace["fusion_mode"], "single_best")

    def test_structured_orbit_query_prefers_wikidata(self):
        trace = self.router.route("月球绕行什么")

        self.assertEqual(trace["selected_sources"], ["wikidata"])
        self.assertIn("wikidata", trace["routing_reason"])

    def test_esa_mission_query_prefers_esa(self):
        trace = self.router.route("JUICE 探测任务研究什么")

        self.assertEqual(trace["selected_sources"], ["esa"])
        self.assertIn("esa", trace["routing_reason"].lower())

    def test_narrative_query_prefers_zh_wikipedia(self):
        trace = self.router.route("太阳为什么会发光")

        self.assertEqual(trace["selected_sources"], ["zh_wikipedia"])
        self.assertEqual(trace["fusion_mode"], "single_best")

    def test_mixed_query_uses_default_multi_source_fusion(self):
        trace = self.router.route("火星质量是多少，为什么这么小")

        self.assertEqual(trace["selected_sources"], ["zh_wikipedia", "wikidata", "nasa"])
        self.assertEqual(trace["fusion_mode"], "multi_source_fusion")


if __name__ == "__main__":
    unittest.main()

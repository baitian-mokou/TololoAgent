import unittest

from src.source_router import SourceRouter


class SourceRouterDefaultAutoTests(unittest.TestCase):
    def setUp(self):
        self.router = SourceRouter()

    def test_numeric_query_prefers_nasa_but_keeps_parallel_candidates(self):
        trace = self.router.route("火星质量是多少")

        self.assertEqual(trace["selected_sources"][0], "nasa")
        self.assertIn("wikidata", trace["selected_sources"])
        self.assertIn("zh_wikipedia", trace["selected_sources"])
        self.assertEqual(trace["fusion_mode"], "peer_source_fusion")

    def test_structured_orbit_query_prefers_wikidata_but_keeps_parallel_candidates(self):
        trace = self.router.route("月球绕行什么")

        self.assertEqual(trace["selected_sources"][0], "wikidata")
        self.assertIn("zh_wikipedia", trace["selected_sources"])
        self.assertIn("wikidata", trace["routing_reason"])

    def test_esa_mission_query_prefers_esa_but_keeps_parallel_candidates(self):
        trace = self.router.route("JUICE 探测任务研究什么")

        self.assertEqual(trace["selected_sources"][0], "esa")
        self.assertIn("nasa", trace["selected_sources"])
        self.assertIn("esa", trace["routing_reason"].lower())

    def test_narrative_query_prefers_zh_wikipedia_but_keeps_parallel_candidates(self):
        trace = self.router.route("太阳为什么会发光")

        self.assertEqual(trace["selected_sources"][0], "zh_wikipedia")
        self.assertIn("nasa", trace["selected_sources"])
        self.assertEqual(trace["fusion_mode"], "peer_source_fusion")

    def test_mixed_query_uses_default_multi_source_fusion(self):
        trace = self.router.route("火星质量是多少，为什么这么小")

        self.assertEqual(trace["selected_sources"], ["nasa", "wikidata", "zh_wikipedia", "esa"])
        self.assertEqual(trace["fusion_mode"], "peer_source_fusion")


if __name__ == "__main__":
    unittest.main()

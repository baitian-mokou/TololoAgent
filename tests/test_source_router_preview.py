import os
import unittest

from src.source_router import ENABLE_ENV, SourceRouterPreview


class SourceRouterPreviewTests(unittest.TestCase):
    def test_router_preview_defaults_to_disabled(self):
        old = os.environ.pop(ENABLE_ENV, None)
        try:
            trace = SourceRouterPreview().route("火星质量是多少")
        finally:
            if old is not None:
                os.environ[ENABLE_ENV] = old

        self.assertFalse(trace["enabled"])
        self.assertFalse(trace["replaces_default_answer"])
        self.assertEqual(trace["preferred_sources"], [])

    def test_router_preview_routes_numerical_fact_when_enabled(self):
        trace = SourceRouterPreview(enabled=True).route("火星质量是多少")

        self.assertTrue(trace["enabled"])
        self.assertEqual(trace["intent"], "structured_numerical_fact")
        self.assertEqual(trace["preferred_sources"], ["nasa", "wikidata", "zh_wikipedia"])
        self.assertFalse(trace["replaces_default_answer"])


if __name__ == "__main__":
    unittest.main()

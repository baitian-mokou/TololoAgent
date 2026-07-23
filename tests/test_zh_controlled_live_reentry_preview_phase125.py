import tempfile
import unittest
from pathlib import Path

from scripts import zh_controlled_live_reentry_preview_phase125 as phase125


class Phase125ControlledLiveReentryPreviewTest(unittest.TestCase):
    def test_probe_limit_is_three(self):
        self.assertLessEqual(len(phase125.probe_titles()), 3)

    def test_success_is_review_only_and_no_body_persisted(self):
        def fetcher(url):
            raw = '{"query":{"pages":{"1":{"extract":"太阳是恒星。"}}}}'.encode("utf-8")
            return 200, "application/json; charset=utf-8", raw, 5

        report = phase125.build_preview(fetcher=fetcher)
        self.assertEqual(report["attempted"], 3)
        self.assertEqual(report["succeeded"], 3)
        self.assertGreater(report["accepted"], 0)
        self.assertEqual(report["queue_allowed"], False)
        self.assertEqual(report["production_ready"], False)
        self.assertTrue(all("body" not in item for item in report["items"]))
        self.assertTrue(all("body_snippet_len" in item for item in report["items"]))

    def test_default_fetcher_is_marked_live_without_body(self):
        original_fetch = phase125._fetch
        phase125._fetch = lambda url: (
            200,
            "application/json; charset=utf-8",
            '{"query":{"pages":{"1":{"extract":"月球是地球的天然卫星。"}}}}'.encode("utf-8"),
            5,
        )
        try:
            report = phase125.build_preview()
        finally:
            phase125._fetch = original_fetch
        self.assertTrue(report["live_probe_used"])

    def test_output_guard(self):
        self.assertFalse(phase125.output_allowed(Path(tempfile.gettempdir()) / "phase125.json"))
        self.assertFalse(phase125.output_allowed(phase125.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase125.output_allowed(phase125.PHASE_DIR / "x.json"))
        self.assertTrue(phase125.output_allowed(phase125.ROOT / "docs" / "phase125.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

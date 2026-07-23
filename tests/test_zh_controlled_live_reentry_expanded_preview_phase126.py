import tempfile
import unittest
from pathlib import Path

from scripts import zh_controlled_live_reentry_expanded_preview_phase126 as phase126


class Phase126ControlledLiveReentryExpandedPreviewTest(unittest.TestCase):
    def test_probe_limit_is_ten(self):
        self.assertLessEqual(len(phase126.probe_titles()), 10)

    def test_success_is_review_only_and_no_body_persisted(self):
        def fetcher(url):
            raw = '{"query":{"pages":{"1":{"extract":"太阳是恒星。"}}}}'.encode("utf-8")
            return 200, "application/json; charset=utf-8", raw, 5

        report = phase126.build_preview(fetcher=fetcher)
        self.assertEqual(report["request_limit"], 10)
        self.assertEqual(report["attempted"], 10)
        self.assertEqual(report["succeeded"], 10)
        self.assertGreater(report["accepted"], 0)
        self.assertFalse(report["queue_allowed"])
        self.assertFalse(report["production_ready"])
        self.assertTrue(all("body" not in item for item in report["items"]))
        self.assertTrue(all("body_snippet_len" in item for item in report["items"]))

    def test_output_guard(self):
        self.assertFalse(phase126.output_allowed(Path(tempfile.gettempdir()) / "phase126.json"))
        self.assertFalse(phase126.output_allowed(phase126.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase126.output_allowed(phase126.PHASE_DIR / "x.json"))
        self.assertTrue(phase126.output_allowed(phase126.ROOT / "docs" / "phase126.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

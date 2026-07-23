import tempfile
import unittest
from pathlib import Path

from scripts import zh_restored_network_recheck_phase124 as phase124


class Phase124RestoredNetworkRecheckTest(unittest.TestCase):
    def test_probe_limit_is_two(self):
        self.assertEqual(len(phase124.probe_plan()), 2)

    def test_reachable_result_is_review_only(self):
        def fetcher(url):
            return 200, "application/json; charset=utf-8", b'{"ok":true}', 4

        report = phase124.build_recheck(fetcher=fetcher)
        self.assertEqual(report["network_verdict"], "mediawiki_network_recovered_review_only")
        self.assertEqual(report["failure_layer"], "none_network_layer_reachable")
        self.assertEqual(report["recommended_next"], "controlled_zh_live_reentry_preview_max_3_titles")
        self.assertFalse(report["queue_allowed"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])

    def test_body_is_not_persisted(self):
        report = phase124.build_recheck(fetcher=lambda url: (200, "application/json", b'{"body":"secret"}', 3))
        self.assertTrue(all("body" not in probe for probe in report["probes"]))
        self.assertTrue(all("body_snippet_len" in probe for probe in report["probes"]))

    def test_output_guard(self):
        self.assertFalse(phase124.output_allowed(Path(tempfile.gettempdir()) / "phase124.json"))
        self.assertFalse(phase124.output_allowed(phase124.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase124.output_allowed(phase124.PHASE_DIR / "x.json"))
        self.assertTrue(phase124.output_allowed(phase124.ROOT / "docs" / "phase124.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

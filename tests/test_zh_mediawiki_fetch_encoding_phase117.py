import tempfile
import unittest
from pathlib import Path

from scripts import zh_mediawiki_fetch_encoding_phase117 as phase117


class Phase117ZhMediaWikiFetchEncodingTest(unittest.TestCase):
    def test_title_url_encoding(self):
        seeds = phase117.zh_seeds()
        self.assertEqual([row["title"] for row in seeds], ["太阳", "太阳系", "水星"])
        self.assertTrue(all("%" in row["extract_url"] for row in seeds))
        self.assertLessEqual(len(seeds), 3)

    def test_utf8_decode_and_extract(self):
        payload = '{"query":{"pages":{"1":{"extract":"太阳是太阳系中心的恒星，主要由氢和氦组成，向周围空间释放光和热。"}}}}'.encode("utf-8")
        text = phase117.decode_payload(payload, "application/json; charset=utf-8")
        self.assertIn("太阳系中心", phase117.extract_plaintext("extracts", text))

    def test_reject_bad_text(self):
        self.assertEqual(phase117.classify_zh_text("å¤ªé˜³æ˜¯乱码"), "rejected")
        self.assertEqual(phase117.classify_zh_text("模板 infobox table caption 123 456 789"), "rejected")
        self.assertEqual(phase117.classify_zh_text("太阳 12345678901234567890"), "rejected")
        self.assertEqual(phase117.classify_zh_text("太阳是太阳系中心的恒星，主要由氢和氦组成，向周围空间释放光和热。"), "accepted")

    def test_report_flags_and_counts_with_failed_fetcher(self):
        report = phase117.build_preview(fetcher=lambda url: (0, "network_error", b"failed"))
        self.assertEqual(report["source_counts"]["attempted"], 3)
        self.assertEqual(report["source_counts"]["failed"], 3)
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])

    def test_output_guard(self):
        self.assertFalse(phase117.output_allowed(Path(tempfile.gettempdir()) / "phase117.json"))
        self.assertFalse(phase117.output_allowed(phase117.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase117.output_allowed(phase117.ROOT / "evaluation" / "four_source_expansion" / "phase117" / "x.json"))
        self.assertTrue(phase117.output_allowed(phase117.ROOT / "docs" / "phase117.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

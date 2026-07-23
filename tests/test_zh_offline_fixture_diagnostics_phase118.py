import tempfile
import unittest
from pathlib import Path

from scripts import zh_offline_fixture_diagnostics_phase118 as phase118


class Phase118ZhOfflineFixtureDiagnosticsTest(unittest.TestCase):
    def test_offline_utf8_fixture_is_accepted(self):
        fixture = phase118.known_good_extract_fixture()
        text = phase118.decode_payload(fixture["payload"], fixture["content_type"])
        narrative = phase118.extract_plaintext(text)
        self.assertEqual(phase118.classify_zh_text(narrative), "accepted")

    def test_rejects_mojibake_table_caption_and_numeric_heavy(self):
        self.assertEqual(phase118.classify_zh_text("å¤ªé˜³æ˜¯ä¸€é¢—æ�’æ˜Ÿ"), "rejected")
        self.assertEqual(phase118.classify_zh_text("模板 infobox table caption 图注"), "rejected")
        self.assertEqual(phase118.classify_zh_text("太阳 1234567890123456789012345"), "rejected")

    def test_url_encoding(self):
        urls = phase118.diagnostic_urls("太阳")
        self.assertIn("%E5%A4%AA%E9%98%B3", urls["known_good_title_probe"])
        self.assertIn("siteinfo", urls["api_status_probe"])

    def test_network_failure_handled_and_flags_false(self):
        report = phase118.build_diagnostics(fetcher=lambda url: (0, "network_error", b"timeout"))
        self.assertTrue(report["encoding_logic_ok"])
        self.assertTrue(report["quality_gate_ok"])
        self.assertEqual(report["network_status"]["api_status_probe"]["status"], "fetch_failed")
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])

    def test_output_guard(self):
        self.assertFalse(phase118.output_allowed(Path(tempfile.gettempdir()) / "phase118.json"))
        self.assertFalse(phase118.output_allowed(phase118.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase118.output_allowed(phase118.ROOT / "evaluation" / "four_source_expansion" / "phase118" / "x.json"))
        self.assertTrue(phase118.output_allowed(phase118.ROOT / "docs" / "phase118.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

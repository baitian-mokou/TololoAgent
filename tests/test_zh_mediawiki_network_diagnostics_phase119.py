import tempfile
import unittest
from pathlib import Path

from scripts import zh_mediawiki_network_diagnostics_phase119 as phase119


class Phase119MediaWikiNetworkDiagnosticsTest(unittest.TestCase):
    def test_probe_limit_is_two(self):
        probes = phase119.probe_plan()
        self.assertEqual(len(probes), 2)
        self.assertEqual([probe["method"] for probe in probes], ["siteinfo_status_probe", "known_good_title_extract_probe"])

    def test_error_handled_and_body_not_persisted(self):
        report = phase119.build_diagnostics(fetcher=lambda url: (0, "network_error", b"timeout", 12))
        self.assertFalse(report["network_reachable"])
        self.assertEqual(report["failure_layer"], "network_or_timeout")
        self.assertTrue(all("body" not in probe for probe in report["probes"]))
        self.assertTrue(all(probe["body_snippet_len"] == 0 for probe in report["probes"]))

    def test_success_summary_flags(self):
        def fetcher(url):
            if "siteinfo" in url:
                return 200, "application/json; charset=utf-8", b'{"query":{"general":{"sitename":"Wikipedia"}}}', 5
            return 200, "application/json; charset=utf-8", "太阳是太阳系中心的恒星。".encode("utf-8"), 6

        report = phase119.build_diagnostics(fetcher=fetcher)
        self.assertTrue(report["network_reachable"])
        self.assertTrue(report["siteinfo_ok"])
        self.assertTrue(report["known_good_title_ok"])
        self.assertFalse(report["queue_allowed"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])

    def test_output_guard(self):
        self.assertFalse(phase119.output_allowed(Path(tempfile.gettempdir()) / "phase119.json"))
        self.assertFalse(phase119.output_allowed(phase119.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase119.output_allowed(phase119.ROOT / "evaluation" / "four_source_expansion" / "phase119" / "x.json"))
        self.assertTrue(phase119.output_allowed(phase119.ROOT / "docs" / "phase119.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

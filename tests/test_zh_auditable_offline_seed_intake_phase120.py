import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts import zh_auditable_offline_seed_intake_phase120 as phase120


class Phase120ZhAuditableOfflineSeedIntakeTest(unittest.TestCase):
    def _seed(self, body=None):
        body = body or "太阳是太阳系中心的恒星，主要由氢和氦组成，通过核聚变释放光和热。"
        return {
            "source_url": "https://zh.wikipedia.org/wiki/太阳",
            "title": "太阳",
            "retrieved_at": "2026-07-23T00:00:00Z",
            "license_or_terms": "CC BY-SA",
            "body": body,
            "expected_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        }

    def test_utf8_chinese_seed_accepted(self):
        row = phase120.validate_seed(self._seed())
        self.assertEqual(row["quality_verdict"], "accepted")
        self.assertEqual(row["review_status"], "pending_manual_review")
        self.assertIn("checksum", row)

    def test_checksum_mismatch_and_missing_provenance_rejected(self):
        bad_checksum = self._seed()
        bad_checksum["expected_sha256"] = "0" * 64
        missing = self._seed()
        del missing["retrieved_at"]
        self.assertEqual(phase120.validate_seed(bad_checksum)["quality_verdict"], "rejected")
        self.assertEqual(phase120.validate_seed(missing)["quality_verdict"], "rejected")

    def test_mojibake_rejected(self):
        self.assertEqual(phase120.validate_seed(self._seed("å¤ªé˜³æ˜¯ä¸€é¢—æ�’æ˜Ÿ"))["quality_verdict"], "rejected")

    def test_report_flags_no_network(self):
        report = phase120.build_preview([self._seed()])
        self.assertEqual(report["counts"]["accepted"], 1)
        self.assertFalse(report["live_fetch_used"])
        self.assertFalse(report["queue_allowed"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])

    def test_output_guard(self):
        self.assertFalse(phase120.output_allowed(Path(tempfile.gettempdir()) / "phase120.json"))
        self.assertFalse(phase120.output_allowed(phase120.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase120.output_allowed(phase120.ROOT / "evaluation" / "four_source_expansion" / "phase120" / "x.json"))
        self.assertTrue(phase120.output_allowed(phase120.ROOT / "docs" / "phase120.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

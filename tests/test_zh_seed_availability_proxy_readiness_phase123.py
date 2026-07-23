import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts import zh_seed_availability_proxy_readiness_phase123 as phase123


class Phase123SeedAvailabilityProxyReadinessTest(unittest.TestCase):
    def _seed(self, title="太阳", body=None):
        body = body or "太阳是太阳系中心的恒星，主要由氢和氦组成，通过核聚变释放光和热。"
        return {
            "source_url": f"https://zh.wikipedia.org/wiki/{title}",
            "title": title,
            "retrieved_at": "2026-07-23T00:00:00Z",
            "license_or_terms": "CC BY-SA",
            "body": body,
            "expected_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        }

    def test_no_seeds_readiness_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = phase123.build_readiness([Path(tmp) / "missing"], env={})
        self.assertEqual(report["external_seed_count"], 0)
        self.assertFalse(report["validation_run"])
        self.assertEqual(report["seed_availability"], "no_external_seeds_found")

    def test_proxy_env_redacted(self):
        report = phase123.build_readiness([], env={"HTTP_PROXY": "http://secret:8080", "HTTPS_PROXY": ""})
        self.assertTrue(report["proxy_env_detected"]["HTTP_PROXY"])
        self.assertFalse(report["proxy_env_detected"]["HTTPS_PROXY"])
        self.assertEqual(report["proxy_env_values"]["HTTP_PROXY"], "<redacted>")

    def test_seed_dir_valid_and_mismatch_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = self._seed("太阳")
            bad = self._seed("水星")
            bad["expected_sha256"] = "0" * 64
            Path(tmp, "seeds.json").write_text(json.dumps([good, bad], ensure_ascii=False), encoding="utf-8")
            report = phase123.build_readiness([Path(tmp)], env={})
        self.assertTrue(report["validation_run"])
        self.assertEqual(report["external_seed_count"], 2)
        self.assertEqual(report["validation_summary"]["counts"]["accepted"], 1)
        self.assertEqual(report["validation_summary"]["counts"]["rejected"], 1)

    def test_output_guard_and_flags(self):
        report = phase123.build_readiness([], env={})
        self.assertFalse(report["live_fetch_used"])
        self.assertFalse(report["queue_allowed"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertFalse(phase123.output_allowed(Path(tempfile.gettempdir()) / "phase123.json"))
        self.assertFalse(phase123.output_allowed(phase123.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase123.output_allowed(phase123.ROOT / "evaluation" / "four_source_expansion" / "phase123" / "x.json"))
        self.assertTrue(phase123.output_allowed(phase123.ROOT / "docs" / "phase123.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

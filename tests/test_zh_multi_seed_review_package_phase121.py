import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import zh_multi_seed_review_package_phase121 as phase121


class Phase121ZhMultiSeedReviewPackageTest(unittest.TestCase):
    def _seed(self, title="太阳", body=None):
        body = body or f"{title}是太阳系相关的天体主题，文本来自可审计离线种子，包含可读中文正文和来源说明。"
        return {
            "source_url": f"https://zh.wikipedia.org/wiki/{title}",
            "title": title,
            "retrieved_at": "2026-07-23T00:00:00Z",
            "license_or_terms": "CC BY-SA",
            "body": body,
            "expected_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        }

    def test_multiple_accepted_fixtures(self):
        report = phase121.build_package([self._seed("太阳"), self._seed("水星")], external_seed_count=2)
        self.assertEqual(report["counts"]["accepted"], 2)
        self.assertFalse(report["fixture_only"])
        self.assertTrue(all(row["review_status"] == "pending_manual_review" for row in report["review_only_candidates"]))

    def test_duplicate_checksum_title_url_rejected(self):
        seed = self._seed("太阳")
        report = phase121.build_package([seed, dict(seed)], external_seed_count=2)
        self.assertEqual(report["counts"]["accepted"], 1)
        self.assertEqual(report["counts"]["rejected"], 1)
        self.assertIn("duplicate_seed", report["records"][1]["reject_reasons"])

    def test_checksum_mismatch_and_missing_provenance_rejected(self):
        bad = self._seed("水星")
        bad["expected_sha256"] = "0" * 64
        missing = self._seed("金星")
        del missing["license_or_terms"]
        report = phase121.build_package([bad, missing], external_seed_count=2)
        self.assertEqual(report["counts"]["rejected"], 2)

    def test_empty_input_dir_fixture_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            seeds, external_count = phase121.load_input_dir(Path(tmp))
        report = phase121.build_package(seeds, external_count)
        self.assertTrue(report["fixture_only"])
        self.assertEqual(report["external_seed_count"], 0)

    def test_output_guard_and_flags(self):
        report = phase121.build_package([self._seed()], external_seed_count=1)
        self.assertFalse(report["live_fetch_used"])
        self.assertFalse(report["queue_allowed"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["preflight_allowed"])
        self.assertFalse(report["apply_approved"])
        self.assertFalse(report["ingest_approved"])
        self.assertFalse(phase121.output_allowed(Path(tempfile.gettempdir()) / "phase121.json"))
        self.assertFalse(phase121.output_allowed(phase121.ROOT / "data" / "raw_json" / "x.json"))
        self.assertTrue(phase121.output_allowed(phase121.ROOT / "evaluation" / "four_source_expansion" / "phase121" / "x.json"))
        self.assertTrue(phase121.output_allowed(phase121.ROOT / "docs" / "phase121.md", allow_docs=True))

    def test_load_input_dir_reads_json_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seed.json"
            path.write_text(json.dumps(self._seed(), ensure_ascii=False), encoding="utf-8")
            seeds, external_count = phase121.load_input_dir(Path(tmp))
        self.assertEqual(external_count, 1)
        self.assertEqual(seeds[0]["title"], "太阳")


if __name__ == "__main__":
    unittest.main()

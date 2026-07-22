import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preview_source_frontier.py"


def load_module():
    spec = importlib.util.spec_from_file_location("preview_source_frontier", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreviewSourceFrontierTests(unittest.TestCase):
    def test_manifest_loader_reads_source_manifest(self):
        module = load_module()

        manifest = module.load_manifest("nasa")

        self.assertEqual(manifest["source_name"], "nasa")
        self.assertIn("science.nasa.gov", manifest["allowed_domains"])
        self.assertTrue(manifest["seed_urls"])

    def test_frontier_filters_domain_exclude_duplicate_and_limit(self):
        module = load_module()
        manifest = {
            "source_name": "nasa",
            "allowed_domains": ["science.nasa.gov"],
            "seed_urls": [
                "https://science.nasa.gov/solar-system/mars/",
                "https://science.nasa.gov/news/mars-update/",
                "https://example.com/solar-system/mars/",
                "https://science.nasa.gov/solar-system/mars/",
                "https://science.nasa.gov/solar-system/jupiter/",
            ],
            "include_path_keywords": ["solar-system"],
            "exclude_path_keywords": ["/news/"],
            "max_depth": 1,
            "max_pages_per_run": 10,
            "crawl_delay": 1.0,
            "notes": "test",
        }

        report = module.build_frontier_preview(manifest, limit=2)
        accepted = report["accepted"]
        skipped = report["skipped"]

        self.assertEqual([item["url"] for item in accepted], [
            "https://science.nasa.gov/solar-system/mars/",
            "https://science.nasa.gov/solar-system/jupiter/",
        ])
        self.assertIn("excluded_path", {item["reason"] for item in skipped})
        self.assertIn("domain_not_allowed", {item["reason"] for item in skipped})
        self.assertIn("duplicate", {item["reason"] for item in skipped})
        self.assertTrue(report["limit_reached"])

    def test_entity_frontier_for_wikidata_is_not_treated_as_network_url(self):
        module = load_module()
        manifest = {
            "source_name": "wikidata",
            "allowed_domains": ["www.wikidata.org", "wikidata.org"],
            "seed_entities": [
                {"entity": "火星", "qid": "Q111"},
                {"entity": "地球", "qid": "Q2"},
                {"entity": "火星", "qid": "Q111"},
            ],
            "include_path_keywords": ["/wiki/"],
            "exclude_path_keywords": [],
            "max_depth": 1,
            "max_pages_per_run": 10,
            "crawl_delay": 1.0,
            "notes": "test",
        }

        report = module.build_frontier_preview(manifest, limit=20)

        self.assertEqual(len(report["accepted"]), 2)
        self.assertEqual(report["accepted"][0]["kind"], "entity")
        self.assertEqual(report["accepted"][0]["url"], "https://www.wikidata.org/wiki/Q111")
        self.assertIn("duplicate", {item["reason"] for item in report["skipped"]})

    def test_cli_dry_run_writes_only_requested_json_outside_data(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "frontier.json"
            data_dir = Path(temp_dir) / "data"

            with mock.patch("scripts.ingest_solar_system_sources.clear_source_ingestion_outputs") as cleanup:
                exit_code = module.main(["--source", "nasa", "--limit", "3", "--json-out", str(out_path)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(out_path.exists())
            self.assertFalse(data_dir.exists())
            cleanup.assert_not_called()

            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_name"], "nasa")
            self.assertLessEqual(len(payload["accepted"]), 3)

    def test_fetch_links_extracts_and_filters_inline_html(self):
        module = load_module()
        manifest = {
            "source_name": "nasa",
            "allowed_domains": ["science.nasa.gov"],
            "seed_urls": ["https://science.nasa.gov/solar-system/"],
            "include_path_keywords": ["solar-system", "planet", "mission"],
            "exclude_path_keywords": ["/news/", "/images/", ".pdf"],
            "max_depth": 1,
            "max_pages_per_run": 10,
            "crawl_delay": 0,
            "notes": "test",
        }
        html = """
        <a href="/solar-system/planets/mars/">Mars</a>
        <a href="https://science.nasa.gov/news/mars-update/">News</a>
        <a href="https://example.com/solar-system/jupiter/">External</a>
        <a href="/solar-system/planets/mars/">Duplicate</a>
        <a href="/wp-content/uploads/fact.pdf">PDF</a>
        """

        def fake_fetch(url, timeout=8):
            return html

        report = module.build_frontier_preview(manifest, limit=10, fetch_links=True, fetcher=fake_fetch)

        accepted_urls = {item["url"] for item in report["accepted"]}
        skipped_reasons = {item["reason"] for item in report["skipped"]}
        self.assertIn("https://science.nasa.gov/solar-system/planets/mars/", accepted_urls)
        self.assertIn("excluded_path", skipped_reasons)
        self.assertIn("domain_not_allowed", skipped_reasons)
        self.assertIn("duplicate", skipped_reasons)

    def test_zero_discovery_fetch_pages_disables_network_expansion(self):
        module = load_module()
        manifest = {
            "source_name": "wikidata",
            "allowed_domains": ["www.wikidata.org"],
            "seed_urls": ["https://www.wikidata.org/wiki/Wikidata:WikiProject_Astronomy"],
            "include_path_keywords": ["WikiProject_Astronomy", "/wiki/Q"],
            "exclude_path_keywords": [],
            "max_depth": 1,
            "max_pages_per_run": 10,
            "max_discovery_fetch_pages": 0,
            "crawl_delay": 0,
            "notes": "test",
        }

        def failing_fetch(url, timeout=8):
            raise AssertionError("fetcher should not be called")

        report = module.build_frontier_preview(manifest, limit=10, fetch_links=True, fetcher=failing_fetch)

        self.assertEqual(report["accepted_count"], 1)
        self.assertEqual(report["discovery_fetches"], 0)

    def test_quality_score_adds_metadata_only_quality_fields_when_enabled(self):
        module = load_module()
        manifest = {
            "source_name": "nasa",
            "allowed_domains": ["science.nasa.gov"],
            "seed_urls": ["https://science.nasa.gov/solar-system/planets/mars/"],
            "include_path_keywords": ["solar-system"],
            "exclude_path_keywords": [],
            "max_depth": 1,
            "max_pages_per_run": 10,
            "crawl_delay": 0,
            "notes": "test",
        }

        plain = module.build_frontier_preview(manifest, limit=1)
        scored = module.build_frontier_preview(manifest, limit=1, quality_score=True)

        self.assertNotIn("quality_score", plain["accepted"][0])
        self.assertEqual(scored["quality_summary"]["total"], 1)
        self.assertEqual(scored["accepted"][0]["quality_input"], "metadata_only")
        self.assertIn("quality_score", scored["accepted"][0])
        self.assertIn(scored["accepted"][0]["quality_triage"], {"accepted", "review_needed", "exploratory", "rejected"})

    def test_quality_score_uses_manifest_entity_data_context(self):
        module = load_module()
        manifest = {
            "source_name": "wikidata",
            "source_mode": "entity_data",
            "topic_taxonomy": ["astronomy", "planetary_science"],
            "quality_gate": {
                "accepted_min_score": 80,
                "review_min_score": 20,
                "allow_exploratory": True,
                "skip_rejected_allowed": False,
            },
            "allowed_domains": ["www.wikidata.org", "wikidata.org"],
            "seed_entities": [{"entity": "火星", "qid": "Q111"}],
            "include_path_keywords": ["/wiki/Q"],
            "exclude_path_keywords": [],
            "max_depth": 1,
            "max_pages_per_run": 10,
            "crawl_delay": 0,
        }

        report = module.build_frontier_preview(manifest, limit=1, quality_score=True)

        self.assertEqual(report["accepted"][0]["quality_triage"], "review_needed")
        self.assertIn("entity_data_source", report["accepted"][0]["quality_labels"])
        self.assertEqual(report["accepted"][0]["quality_metrics"]["source_mode"], "entity_data")

    def test_cli_previews_custom_manifest_offline_with_quality_fields(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = ROOT / "configs" / "source_manifests" / "examples" / "academic_example.json"
            out_path = Path(temp_dir) / "academic_frontier.json"

            exit_code = module.main([
                "--manifest",
                str(manifest_path),
                "--quality-score",
                "--limit",
                "3",
                "--json-out",
                str(out_path),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_name"], "academic_example")
            self.assertFalse(payload["source_registered"])
            self.assertFalse(payload["network_access"])
            self.assertTrue(payload["manifest_validation"]["passed"])
            self.assertIn("quality_score", payload["accepted"][0])

    def test_custom_manifest_fetch_links_is_forced_offline(self):
        module = load_module()

        manifest = module.load_manifest_from_path(
            ROOT / "configs" / "source_manifests" / "examples" / "academic_example.json"
        )

        def failing_fetch(url, timeout=8):
            raise AssertionError("custom manifest preview should not fetch links")

        report = module.build_frontier_preview(
            manifest,
            limit=3,
            fetch_links=True,
            fetcher=failing_fetch,
            custom_manifest=True,
        )

        self.assertFalse(report["network_access"])
        self.assertEqual(report["discovery_fetches"], 0)
        self.assertTrue(report["manifest_validation"]["warnings"])

    def test_preflight_manifest_rejects_invalid_manifest(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "bad.json"
            manifest_path.write_text(json.dumps({"source_name": "bad"}), encoding="utf-8")

            exit_code = module.main([
                "--manifest",
                str(manifest_path),
                "--preflight-manifest",
                "--limit",
                "1",
            ])

            self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()

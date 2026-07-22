import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ingest_manifest_frontier.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ingest_manifest_frontier", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IngestManifestFrontierTests(unittest.TestCase):
    def test_low_quality_urls_are_skipped_by_manifest_rules(self):
        module = load_module()
        manifest = {
            "source_name": "esa",
            "allowed_domains": ["www.esa.int"],
            "include_path_keywords": ["Science_Exploration"],
            "exclude_path_keywords": ["/Newsroom/", "/ESA_Multimedia/Images/", ".pdf"],
            "max_depth": 1,
            "max_pages_per_run": 10,
            "crawl_delay": 0,
        }

        self.assertEqual(
            module.skip_reason_for_url(
                "https://www.esa.int/ESA_Multimedia/Images/Mars", manifest
            ),
            "excluded_path",
        )
        self.assertEqual(
            module.skip_reason_for_url("https://example.com/Science_Exploration/Mars", manifest),
            "domain_not_allowed",
        )
        self.assertEqual(
            module.skip_reason_for_url("https://www.esa.int/?search=Rosetta", manifest),
            "excluded_path",
        )

    def test_raw_only_ingest_writes_temp_raw_and_report_without_cleanup(self):
        module = load_module()
        frontier = {
            "source_name": "nasa",
            "accepted": [
                {
                    "kind": "url",
                    "url": "https://science.nasa.gov/solar-system/planets/mars/",
                    "depth": 1,
                    "reason": "accepted",
                }
            ],
        }
        manifest = {
            "source_name": "nasa",
            "allowed_domains": ["science.nasa.gov"],
            "include_path_keywords": ["solar-system"],
            "exclude_path_keywords": ["/news/"],
            "max_depth": 1,
            "max_pages_per_run": 10,
            "crawl_delay": 0,
        }

        def fake_fetch(url, timeout=15):
            return {
                "url": url,
                "content_type": "text/html; charset=utf-8",
                "body": "<html><head><title>Mars - NASA Science</title></head>"
                "<body><main>Mars is a planet. " + ("science text " * 40) + "</main></body></html>",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with mock.patch("scripts.ingest_solar_system_sources.clear_source_ingestion_outputs") as cleanup:
                report = module.ingest_frontier(
                    source_name="nasa",
                    manifest=manifest,
                    frontier=frontier,
                    limit=5,
                    delay=0,
                    raw_root=root / "data" / "raw_json",
                    report_path=root / "evaluation" / "ingestion" / "nasa_manifest_ingestion_report.json",
                    fetcher=fake_fetch,
                    min_text_length=20,
                )

            cleanup.assert_not_called()
            self.assertEqual(report["fetched_count"], 1)
            self.assertEqual(report["failed_count"], 0)
            raw_files = list((root / "data" / "raw_json" / "nasa").glob("*.json"))
            self.assertEqual(len(raw_files), 1)
            payload = json.loads(raw_files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["source_name"], "nasa")
            self.assertIn("Mars", payload["title"])
            self.assertTrue((root / "evaluation" / "ingestion" / "nasa_manifest_ingestion_report.json").exists())

    def test_quality_report_is_optional_and_does_not_change_default_ingest(self):
        module = load_module()
        frontier = {
            "source_name": "nasa",
            "accepted": [{
                "kind": "url",
                "url": "https://science.nasa.gov/solar-system/planets/mars/",
                "depth": 1,
                "reason": "accepted",
            }],
        }
        manifest = {
            "source_name": "nasa",
            "allowed_domains": ["science.nasa.gov"],
            "include_path_keywords": ["solar-system"],
            "exclude_path_keywords": [],
            "max_depth": 1,
            "max_pages_per_run": 10,
            "crawl_delay": 0,
        }

        def fake_fetch(url, timeout=15):
            return {
                "url": url,
                "content_type": "text/html",
                "body": "<html><head><title>Mars Fact Sheet</title></head><body>"
                "<table><tr><th>Mass</th><td>0.64</td></tr></table>"
                "<p>Mars planet solar system atmosphere orbit mass radius diameter mission reference.</p>"
                "</body></html>",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plain = module.ingest_frontier(
                source_name="nasa",
                manifest=manifest,
                frontier=frontier,
                limit=1,
                delay=0,
                raw_root=root / "plain" / "raw",
                report_path=root / "plain" / "report.json",
                fetcher=fake_fetch,
                min_text_length=20,
            )
            scored = module.ingest_frontier(
                source_name="nasa",
                manifest=manifest,
                frontier=frontier,
                limit=1,
                delay=0,
                raw_root=root / "scored" / "raw",
                report_path=root / "scored" / "report.json",
                fetcher=fake_fetch,
                min_text_length=20,
                quality_report=True,
            )

        self.assertNotIn("quality_summary", plain)
        self.assertNotIn("quality_score", plain["items"][0])
        self.assertIn("quality_summary", scored)
        self.assertEqual(scored["quality_summary"]["total"], 1)
        self.assertIn("quality_score", scored["items"][0])

    def test_quality_report_uses_manifest_quality_context(self):
        module = load_module()
        frontier = {
            "source_name": "nasa",
            "accepted": [{
                "kind": "url",
                "url": "https://science.nasa.gov/mission/juno/",
                "depth": 1,
                "reason": "accepted",
            }],
        }
        manifest = {
            "source_name": "nasa",
            "source_mode": "official_science",
            "topic_taxonomy": ["astronomy", "planetary_science"],
            "quality_gate": {
                "accepted_min_score": 65,
                "review_min_score": 35,
                "allow_exploratory": True,
                "skip_rejected_allowed": True,
            },
            "allowed_domains": ["science.nasa.gov"],
            "include_path_keywords": ["mission"],
            "exclude_path_keywords": [],
            "max_depth": 1,
            "max_pages_per_run": 10,
            "crawl_delay": 0,
        }

        def fake_fetch(url, timeout=15):
            return {
                "url": url,
                "content_type": "text/html",
                "body": "<html><head><title>Juno Mission</title></head><body>"
                "<p>Juno is a NASA spacecraft mission studying Jupiter, planetary science, orbit and atmosphere.</p>"
                "</body></html>",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = module.ingest_frontier(
                source_name="nasa",
                manifest=manifest,
                frontier=frontier,
                limit=1,
                delay=0,
                raw_root=root / "raw",
                report_path=root / "report.json",
                fetcher=fake_fetch,
                min_text_length=20,
                quality_report=True,
            )

        self.assertEqual(report["items"][0]["quality_metrics"]["source_mode"], "official_science")
        self.assertIn(report["items"][0]["quality_triage"], {"accepted", "review_needed"})

    def test_skip_rejected_only_applies_when_explicitly_enabled(self):
        module = load_module()
        frontier = {
            "source_name": "nasa",
            "accepted": [{
                "kind": "url",
                "url": "https://science.nasa.gov/solar-system/gallery/mars-images/",
                "depth": 1,
                "reason": "accepted",
            }],
        }
        manifest = {
            "source_name": "nasa",
            "allowed_domains": ["science.nasa.gov"],
            "include_path_keywords": ["solar-system"],
            "exclude_path_keywords": [],
            "max_depth": 1,
            "max_pages_per_run": 10,
            "crawl_delay": 0,
        }

        def fake_fetch(url, timeout=15):
            return {
                "url": url,
                "content_type": "text/html",
                "body": "<html><head><title>Mars image gallery</title></head>"
                "<body><p>Images and videos from Mars gallery.</p></body></html>",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kept = module.ingest_frontier(
                source_name="nasa",
                manifest=manifest,
                frontier=frontier,
                limit=1,
                delay=0,
                raw_root=root / "kept" / "raw",
                report_path=root / "kept" / "report.json",
                fetcher=fake_fetch,
                min_text_length=1,
                quality_report=True,
            )
            skipped = module.ingest_frontier(
                source_name="nasa",
                manifest=manifest,
                frontier=frontier,
                limit=1,
                delay=0,
                raw_root=root / "skipped" / "raw",
                report_path=root / "skipped" / "report.json",
                fetcher=fake_fetch,
                min_text_length=1,
                quality_report=True,
                skip_rejected=True,
            )

        self.assertEqual(kept["fetched_count"], 1)
        self.assertEqual(skipped["fetched_count"], 0)
        self.assertEqual(skipped["skipped_count"], 1)
        self.assertEqual(skipped["items"][0]["reason"], "skipped_quality_rejected")

    def test_cli_preflight_rejects_invalid_manifest_before_ingest(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest_dir = temp_root / "manifests"
            frontier_dir = temp_root / "frontiers"
            manifest_dir.mkdir()
            frontier_dir.mkdir()
            (manifest_dir / "nasa.json").write_text(json.dumps({"source_name": "nasa"}), encoding="utf-8")
            (frontier_dir / "nasa_frontier.json").write_text(json.dumps({"accepted": []}), encoding="utf-8")

            with mock.patch.object(module, "MANIFEST_DIR", manifest_dir), mock.patch.object(module, "FRONTIER_DIR", frontier_dir):
                exit_code = module.main(["--source", "nasa", "--preflight-manifest"])

            self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()

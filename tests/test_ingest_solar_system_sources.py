import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ingest_solar_system_sources import (
    RAW_SOURCES,
    ControlledSourceConfig,
    DiscoveredHtmlPage,
    _build_esa_records,
    _build_nasa_records,
    _build_wikidata_records,
    _build_zh_record_from_raw_payload,
    _build_zh_records,
    _load_source_state,
    _materialize_shadow_namespace,
    _nasa_record_from_payload,
    _save_source_state,
    _source_raw_record_paths,
    clear_source_ingestion_outputs,
    ingest_records_for_source,
    is_allowed_source_url,
    limit_seed_items,
    source_cleanup_targets,
)


class IngestSolarSystemSourcesTests(unittest.TestCase):
    def test_nasa_query_fixture_exists_for_low_coverage_local_fallback(self):
        fixture_path = Path(__file__).resolve().parents[1] / "data" / "source_fixtures" / "nasa" / "query_fixture.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["source_name"], "nasa")
        titles = {record["title"] for record in payload["records"]}
        self.assertIn("火星", titles)
        self.assertIn("火卫二", titles)

    def test_limit_is_applied_to_seed_items(self):
        seeds = ["a", "b", "c"]
        self.assertEqual(limit_seed_items(seeds, 2), ["a", "b"])
        self.assertEqual(limit_seed_items(seeds, 20), seeds)

    def test_non_allowlist_url_is_rejected(self):
        config = ControlledSourceConfig(
            source_name="nasa",
            allowed_domains=("science.nasa.gov", "nssdc.gsfc.nasa.gov"),
            seed_items=[],
        )

        self.assertTrue(is_allowed_source_url(config, "https://science.nasa.gov/mars/facts/"))
        self.assertFalse(is_allowed_source_url(config, "https://example.com/mars"))

    def test_cross_domain_url_is_rejected_even_if_path_looks_valid(self):
        config = ControlledSourceConfig(
            source_name="esa",
            allowed_domains=("www.esa.int",),
            seed_items=[],
        )

        self.assertFalse(is_allowed_source_url(config, "https://science.nasa.gov/solar-system/juice"))

    def test_raw_json_is_written_into_source_specific_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_root = root / "data" / "raw_json"
            triples_root = root / "data" / "triples"
            evaluation_root = root / "evaluation" / "ingestion"

            report = ingest_records_for_source(
                source_name="wikidata",
                records=[{
                    "raw_id": "mars",
                    "raw_payload": {"title": "火星", "qid": "Q111"},
                    "title": "火星",
                    "triples": [{"subject": "火星", "relation": "HAS_MASS", "object": "6.4171e23 kg"}],
                    "narratives": [{"section": "概述", "content": "火星是太阳系行星。"}],
                    "source_url": "https://www.wikidata.org/wiki/Q111",
                }],
                base_dir=str(root),
                raw_root=str(raw_root),
                triples_root=str(triples_root),
                evaluation_root=str(evaluation_root),
                materialize_graph=False,
                materialize_chroma=False,
            )

            raw_dir = raw_root / "wikidata"
            raw_files = sorted(raw_dir.glob("*.json"))
            self.assertEqual(len(raw_files), 1)
            payload = json.loads(raw_files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["title"], "火星")
            self.assertEqual(report["raw_records_written"], 1)
            self.assertEqual(report["triples_written"], 1)
            self.assertEqual(report["narratives_written"], 1)

    def test_ingest_removes_stale_processed_files_before_writing_current_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_root = root / "data" / "raw_json"
            triples_root = root / "data" / "triples"
            evaluation_root = root / "evaluation" / "ingestion"
            stale_dir = triples_root / "esa"
            stale_dir.mkdir(parents=True)
            (stale_dir / "旧任务_triples.json").write_text("[]", encoding="utf-8")
            (stale_dir / "旧任务_narratives.json").write_text("[]", encoding="utf-8")

            ingest_records_for_source(
                source_name="esa",
                records=[{
                    "raw_id": "juice",
                    "raw_payload": {"title": "JUICE"},
                    "title": "JUICE",
                    "triples": [{"subject": "JUICE", "relation": "HAS_MISSION_TARGET", "object": "木星"}],
                    "narratives": [{"section": "任务", "content": "JUICE 探测木星。"}],
                    "source_url": "https://www.esa.int/Science_Exploration/Space_Science/Juice",
                }],
                base_dir=str(root),
                raw_root=str(raw_root),
                triples_root=str(triples_root),
                evaluation_root=str(evaluation_root),
                materialize_graph=False,
                materialize_chroma=False,
            )

            self.assertFalse((stale_dir / "旧任务_triples.json").exists())
            self.assertFalse((stale_dir / "旧任务_narratives.json").exists())
            self.assertEqual(len(list(stale_dir.glob("*_triples.json"))), 1)
            self.assertEqual(len(list(stale_dir.glob("*_narratives.json"))), 1)

    def test_ingest_report_preserves_requested_source_label(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = ingest_records_for_source(
                source_name="nasa",
                records=[{
                    "raw_id": "venus",
                    "raw_payload": {"title": "金星"},
                    "title": "金星",
                    "triples": [{"subject": "金星", "relation": "HAS_RADIUS", "object": "6051.8 km"}],
                    "narratives": [],
                    "source_url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/venusfact.html",
                }],
                base_dir=str(root),
                raw_root=str(root / "data" / "raw_json"),
                triples_root=str(root / "data" / "triples"),
                evaluation_root=str(root / "evaluation" / "ingestion"),
            )

        self.assertEqual(report["source"], "nasa")

    def test_all_known_sources_are_declared(self):
        self.assertEqual(sorted(RAW_SOURCES), ["esa", "nasa", "wikidata", "zh_wikipedia"])

    def test_wikidata_auto_mode_prefers_fixture_without_treating_live_unavailable_as_failure(self):
        with patch("scripts.ingest_solar_system_sources._load_wikidata_raw_payload", return_value=None), patch(
            "scripts.ingest_solar_system_sources.WikidataFixtureAdapter.fetch_live",
            side_effect=RuntimeError("offline"),
        ):
            records, warnings, errors, skipped = _build_wikidata_records(limit=2, mode="auto")

        self.assertGreaterEqual(len(records), 2)
        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])

    def test_wikidata_auto_mode_treats_http_429_as_warning_and_pending_not_hard_error(self):
        config = ControlledSourceConfig(
            source_name="wikidata",
            allowed_domains=("www.wikidata.org", "wikidata.org"),
            seed_items=[
                {"entity": "火星", "qid": "Q111"},
                {"entity": "不存在条目", "qid": "Q999999999"},
            ],
            max_depth=0,
        )

        with patch("scripts.ingest_solar_system_sources.source_config_for", return_value=config), patch(
            "scripts.ingest_solar_system_sources._load_wikidata_raw_payload",
            return_value=None,
        ), patch(
            "scripts.ingest_solar_system_sources.WikidataFixtureAdapter.fetch_live",
            side_effect=RuntimeError("HTTP Error 429: Too Many Requests"),
        ):
            records, warnings, errors, skipped = _build_wikidata_records(limit=2, mode="auto")

        self.assertGreaterEqual(len(records), 1)
        self.assertTrue(any("429" in warning for warning in warnings))
        self.assertTrue(any("pending missing record" in warning for warning in warnings))
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])

    def test_wikidata_live_mode_expands_live_neighbors_with_depth_control(self):
        config = ControlledSourceConfig(
            source_name="wikidata",
            allowed_domains=("www.wikidata.org", "wikidata.org"),
            seed_items=[{"entity": "火星", "qid": "Q111"}],
            max_depth=1,
        )

        def fake_fetch_live(adapter_self):
            if adapter_self.entity == "Q111":
                return {
                    "entities": {
                        "Q111": {
                            "labels": {"zh": {"value": "火星"}},
                            "claims": {
                                "P397": [{
                                    "id": "Q111$orbit",
                                    "mainsnak": {"datavalue": {"value": {"id": "Q2"}}},
                                }]
                            },
                        }
                    }
                }
            if adapter_self.entity == "Q2":
                return {
                    "entities": {
                        "Q2": {
                            "labels": {"zh": {"value": "地球"}},
                            "claims": {},
                        }
                    }
                }
            raise AssertionError(f"unexpected entity {adapter_self.entity}")

        with patch("scripts.ingest_solar_system_sources.source_config_for", return_value=config), patch(
            "scripts.ingest_solar_system_sources._load_first_existing_json",
            return_value={"records": []},
        ), patch(
            "scripts.ingest_solar_system_sources._load_wikidata_raw_payload",
            return_value=None,
        ), patch(
            "scripts.ingest_solar_system_sources.WikidataFixtureAdapter.fetch_live",
            new=fake_fetch_live,
        ), patch(
            "scripts.ingest_solar_system_sources._cache_live_raw_payload",
        ):
            records, warnings, errors, skipped = _build_wikidata_records(limit=2, mode="live")

        self.assertEqual([record["title"] for record in records], ["火星", "地球"])
        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])

    def test_nasa_auto_mode_uses_discovery_fixture_before_bundled_fallback(self):
        with patch("scripts.ingest_solar_system_sources._discover_nasa_candidate_pages", return_value=([], [])), patch(
            "scripts.ingest_solar_system_sources._source_raw_record_paths",
            return_value=[],
        ):
            records, warnings, errors, skipped = _build_nasa_records(limit=3, mode="auto")

        self.assertEqual(len(records), 3)
        self.assertIn(records[0]["title"], {"水星", "金星", "地球", "月球", "火星", "木星", "土星", "天王星", "海王星", "冥王星"})
        self.assertFalse(any("bundled Mars fact-sheet fallback" in warning for warning in warnings))
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])

    def test_nasa_cached_raw_skips_noisy_pages_before_resume_limit_is_satisfied(self):
        noisy_payload = {
            "title": "10 Things to Know About Planetary Analogs - NASA Science",
            "url": "https://science.nasa.gov/solar-system/10-things-to-know-about-planetary-analogs/",
            "html": "<html><head><title>10 Things to Know About Planetary Analogs - NASA Science</title></head><body>feature story</body></html>",
            "fetched_at": "2026-06-28T00:00:00+00:00",
        }
        good_payload = {
            "title": "火星",
            "url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
            "html": "<html><head><title>Mars Fact Sheet</title></head><body><table><tr><th>Field</th><th>Mars</th></tr><tr><td>Mass (10^24 kg)</td><td>0.64171</td></tr><tr><td>Mean radius (km)</td><td>3389.5</td></tr></table></body></html>",
            "fetched_at": "2026-06-28T00:00:00+00:00",
        }

        with patch(
            "scripts.ingest_solar_system_sources._source_raw_record_paths",
            return_value=[Path("nasa_noisy.json"), Path("mars_cached.json")],
        ), patch(
            "scripts.ingest_solar_system_sources._load_first_existing_json",
            return_value={"records": []},
        ), patch(
            "scripts.ingest_solar_system_sources.load_json",
            side_effect=[noisy_payload, good_payload],
        ), patch(
            "scripts.ingest_solar_system_sources._discover_nasa_candidate_pages",
            side_effect=AssertionError("discovery should not run when a high-value cached raw already satisfies the limit"),
        ):
            records, warnings, errors, skipped = _build_nasa_records(limit=1, mode="auto")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "火星")
        self.assertIn(noisy_payload["url"], skipped)
        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])

    def test_nasa_auto_mode_emits_low_coverage_warning_when_retained_fact_pages_are_sparse(self):
        fixture_payload = {
            "records": [{
                "title": "火星",
                "source_url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
                "html": "<table><tr><th>Field</th><th>Mars</th></tr><tr><td>Mass (10^24 kg)</td><td>0.64171</td></tr><tr><td>Mean radius (km)</td><td>3389.5</td></tr></table>",
                "fetched_at": "2026-06-28T00:00:00+00:00",
            }]
        }

        with patch("scripts.ingest_solar_system_sources._source_raw_record_paths", return_value=[]), patch(
            "scripts.ingest_solar_system_sources._discover_nasa_candidate_pages",
            return_value=([], []),
        ), patch(
            "scripts.ingest_solar_system_sources._load_first_existing_json",
            return_value=fixture_payload,
        ):
            records, warnings, errors, skipped = _build_nasa_records(limit=80, mode="auto")

        self.assertEqual(len(records), 1)
        self.assertTrue(any("low coverage" in warning for warning in warnings))
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])

    def test_nasa_mars_maintenance_page_uses_strict_table_fallback(self):
        from src.source_adapters.nasa import NasaPipelineAdapter

        record = _nasa_record_from_payload(
            NasaPipelineAdapter(timeout=1),
            {
                "title": "火星",
                "source_url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
                "html": "<html><title>NASA Space Science Data Coordinated Archive Status - NASA</title><body>temporarily offline for maintenance</body></html>",
                "fetched_at": "2026-01-01T00:00:00+00:00",
            },
        )

        by_relation = {item["relation"]: item["object"] for item in record["triples"]}
        self.assertEqual(by_relation["HAS_MASS"], "6.4171e23 kg")
        self.assertEqual(by_relation["HAS_RADIUS"], "3389.5 km")
        self.assertIn("HAS_ATMOSPHERE", by_relation)

    def test_build_zh_record_from_raw_payload_extracts_venus_radius_from_html(self):
        payload = {
            "title": "金星",
            "category": "行星",
            "url": "https://zh.wikipedia.org/wiki/金星",
            "html": """
                <html><body>
                <table class="infobox">
                  <tr><th>平均半徑</th><td>6,051.8 ± 1.0km</td></tr>
                </table>
                <p>金星是太阳系的一颗行星。</p>
                </body></html>
            """,
        }

        record, error = _build_zh_record_from_raw_payload(payload)

        self.assertEqual(error, "")
        self.assertIsNotNone(record)
        radius_values = [item["object"] for item in record["triples"] if item["relation"] == "HAS_RADIUS"]
        self.assertEqual(radius_values, ["6051.8 km"])

    def test_build_zh_record_from_raw_payload_extracts_mercury_radius_from_html(self):
        payload = {
            "title": "水星",
            "category": "行星",
            "url": "https://zh.wikipedia.org/wiki/水星",
            "html": """
                <html><body>
                <table class="infobox">
                  <tr><th>平均半徑</th><td>2,440.7 ± 1.0 km</td></tr>
                </table>
                <p>水星是太阳系的一颗行星。</p>
                </body></html>
            """,
        }

        record, error = _build_zh_record_from_raw_payload(payload)

        self.assertEqual(error, "")
        self.assertIsNotNone(record)
        radius_values = [item["object"] for item in record["triples"] if item["relation"] == "HAS_RADIUS"]
        self.assertEqual(radius_values, ["2440.7 km"])

    def test_build_zh_records_prefers_raw_html_preprocess_over_legacy_triples(self):
        config = ControlledSourceConfig(
            source_name="zh_wikipedia",
            allowed_domains=("zh.wikipedia.org",),
            seed_items=[{"title": "金星", "category": "行星"}],
            timeout=12,
            crawl_delay=2.5,
            max_depth=1,
        )
        payload = {
            "title": "金星",
            "category": "行星",
            "url": "https://zh.wikipedia.org/wiki/金星",
            "html": """
                <html><body>
                <table class="infobox">
                  <tr><th>平均半徑</th><td>6,051.8 ± 1.0km</td></tr>
                </table>
                <p>金星是太阳系的一颗行星。</p>
                </body></html>
            """,
        }

        def fail_legacy_read(path):
            if str(path).endswith("_triples.json") or str(path).endswith("_narratives.json"):
                raise AssertionError("legacy triples fallback should not run when raw HTML is available")
            return None

        with patch("scripts.ingest_solar_system_sources.source_config_for", return_value=config), patch(
            "scripts.ingest_solar_system_sources._zh_seed_payload",
            return_value=payload,
        ), patch(
            "scripts.ingest_solar_system_sources._load_json_if_exists",
            side_effect=fail_legacy_read,
        ):
            records, warnings, errors, skipped = _build_zh_records(limit=1, mode="offline")

        self.assertEqual(len(records), 1)
        radius_values = [item["object"] for item in records[0]["triples"] if item["relation"] == "HAS_RADIUS"]
        self.assertEqual(radius_values, ["6051.8 km"])
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])
        self.assertEqual(warnings, [])

    def test_nasa_live_mode_expands_multiple_candidate_pages_and_honors_limit(self):
        candidate_pages = [
            DiscoveredHtmlPage(
                url="https://nssdc.gsfc.nasa.gov/planetary/factsheet/mercuryfact.html",
                html="<html><head><title>Mercury Fact Sheet</title></head><body><table><tr><th>Field</th><th>Mercury</th></tr><tr><td>Mass (10^24 kg)</td><td>0.33011</td></tr><tr><td>Mean radius (km)</td><td>2439.7</td></tr></table></body></html>",
                depth=1,
                title="Mercury Fact Sheet",
            ),
            DiscoveredHtmlPage(
                url="https://nssdc.gsfc.nasa.gov/planetary/factsheet/venusfact.html",
                html="<html><head><title>Venus Fact Sheet</title></head><body><table><tr><th>Field</th><th>Venus</th></tr><tr><td>Mass (10^24 kg)</td><td>4.8675</td></tr><tr><td>Mean radius (km)</td><td>6051.8</td></tr></table></body></html>",
                depth=1,
                title="Venus Fact Sheet",
            ),
            DiscoveredHtmlPage(
                url="https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html",
                html="<html><head><title>Earth Fact Sheet</title></head><body><table><tr><th>Field</th><th>Earth</th></tr><tr><td>Mass (10^24 kg)</td><td>5.9724</td></tr><tr><td>Mean radius (km)</td><td>6371.0</td></tr></table></body></html>",
                depth=2,
                title="Earth Fact Sheet",
            ),
        ]

        with patch("scripts.ingest_solar_system_sources._discover_nasa_candidate_pages", return_value=(candidate_pages, candidate_pages)), patch(
            "scripts.ingest_solar_system_sources._source_raw_record_paths",
            return_value=[],
        ):
            records, warnings, errors, skipped = _build_nasa_records(limit=2, mode="live")

        self.assertEqual(len(records), 2)
        self.assertEqual([record["title"] for record in records], ["水星", "金星"])
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])
        self.assertEqual(warnings, [])

    def test_esa_live_mode_expands_multiple_candidate_pages_and_honors_limit(self):
        candidate_pages = [
            DiscoveredHtmlPage(
                url="https://www.esa.int/Science_Exploration/Space_Science/Juice",
                html="<html><head><title>JUICE</title></head><body>JUICE mission to Jupiter, Europa, Ganymede and Callisto.</body></html>",
                depth=1,
                title="JUICE",
            ),
            DiscoveredHtmlPage(
                url="https://www.esa.int/Science_Exploration/Space_Science/Mars_Express",
                html="<html><head><title>Mars Express</title></head><body>Mars Express mission studies Mars.</body></html>",
                depth=1,
                title="Mars Express",
            ),
            DiscoveredHtmlPage(
                url="https://www.esa.int/Science_Exploration/Space_Science/SMART-1",
                html="<html><head><title>SMART-1</title></head><body>SMART-1 lunar mission explores the Moon.</body></html>",
                depth=2,
                title="SMART-1",
            ),
        ]

        with patch("scripts.ingest_solar_system_sources._load_first_existing_json", return_value={"records": []}), patch(
            "scripts.ingest_solar_system_sources._discover_esa_candidate_pages",
            return_value=(candidate_pages, candidate_pages),
        ), patch(
            "scripts.ingest_solar_system_sources._source_raw_record_paths",
            return_value=[],
        ):
            records, warnings, errors, skipped = _build_esa_records(limit=2, mode="live")

        self.assertEqual(len(records), 2)
        self.assertEqual(set(record["title"] for record in records), {"JUICE", "Mars Express"})
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])
        self.assertEqual(warnings, [])

    def test_esa_records_prioritize_core_fixture_before_raw_pages(self):
        config = ControlledSourceConfig(
            source_name="esa",
            allowed_domains=("www.esa.int", "esa.int"),
            seed_items=[
                {
                    "title": "SMART-1",
                    "url": "https://www.esa.int/Science_Exploration/Space_Science/SMART-1",
                    "targets": ["月球"],
                }
            ],
        )
        fixture_payload = {
            "records": [{
                "title": "SMART-1",
                "triples": [{"subject": "SMART-1", "relation": "ORBITS", "object": "月球"}],
                "narratives": [{"section": "任务", "content": "SMART-1 绕月球运行。"}],
            }]
        }
        raw_payload = {
            "title": "ESA - Facts about Mars",
            "url": "https://www.esa.int/Science_Exploration/Space_Science/Mars_Express/Facts_about_Mars",
            "html": "<html><head><title>ESA - Facts about Mars</title></head><body>Mars Express studies Mars.</body></html>",
        }

        with patch("scripts.ingest_solar_system_sources.source_config_for", return_value=config), patch(
            "scripts.ingest_solar_system_sources._load_first_existing_json",
            return_value=fixture_payload,
        ), patch("scripts.ingest_solar_system_sources._source_raw_record_paths", return_value=[Path("raw_mars.json")]), patch(
            "scripts.ingest_solar_system_sources.load_json",
            return_value=raw_payload,
        ):
            records, warnings, errors, skipped = _build_esa_records(limit=1, mode="offline")

        self.assertEqual([record["title"] for record in records], ["SMART-1"])
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])
        self.assertEqual(warnings, [])

    def test_esa_live_mode_skips_noisy_primary_site_pages(self):
        config = ControlledSourceConfig(
            source_name="esa",
            allowed_domains=("www.esa.int", "esa.int"),
            seed_items=[],
            max_depth=2,
        )
        candidate_pages = [
            DiscoveredHtmlPage(
                url="https://www.esa.int/Science_Exploration/Space_Science/Ash_creeps_across_Mars",
                html="<html><head><title>ESA - Ash creeps across Mars</title></head><body>image feature</body></html>",
                depth=1,
                title="ESA - Ash creeps across Mars",
            ),
            DiscoveredHtmlPage(
                url="https://www.esa.int/Science_Exploration/Space_Science/Juice",
                html="<html><head><title>JUICE</title></head><body>JUICE mission to Jupiter, Europa, Ganymede and Callisto.</body></html>",
                depth=1,
                title="JUICE",
            ),
        ]

        with patch("scripts.ingest_solar_system_sources.source_config_for", return_value=config), patch(
            "scripts.ingest_solar_system_sources._load_first_existing_json",
            return_value={"records": []},
        ), patch("scripts.ingest_solar_system_sources._discover_esa_candidate_pages", return_value=(candidate_pages, candidate_pages)), patch(
            "scripts.ingest_solar_system_sources._source_raw_record_paths",
            return_value=[],
        ):
            records, warnings, errors, skipped = _build_esa_records(limit=2, mode="live")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "JUICE")
        self.assertIn(candidate_pages[0].url, skipped)
        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])

    def test_cached_nasa_raw_records_allow_resume_without_refetching_discovery(self):
        cached_payload = {
            "title": "火星",
            "url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
            "html": "<html><head><title>Mars Fact Sheet</title></head><body><table><tr><th>Field</th><th>Mars</th></tr><tr><td>Mass (10^24 kg)</td><td>0.64171</td></tr><tr><td>Mean radius (km)</td><td>3389.5</td></tr></table></body></html>",
            "fetched_at": "2026-06-28T00:00:00+00:00",
        }

        with patch("scripts.ingest_solar_system_sources._source_raw_record_paths", return_value=[Path("mars_cached.json")]), patch(
            "scripts.ingest_solar_system_sources.load_json",
            return_value=cached_payload,
        ), patch(
            "scripts.ingest_solar_system_sources._discover_nasa_candidate_pages",
            side_effect=AssertionError("discovery should not run when cached raw already satisfies the limit"),
        ):
            records, warnings, errors, skipped = _build_nasa_records(limit=1, mode="auto")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "火星")
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])
        self.assertEqual(warnings, [])

    def test_source_state_and_raw_record_paths_support_resume_without_treating_state_as_raw_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_root = Path(tmpdir) / "data" / "raw_json"
            nasa_raw_dir = raw_root / "nasa"
            nasa_raw_dir.mkdir(parents=True)
            (nasa_raw_dir / "__crawl_state__.json").write_text("{}", encoding="utf-8")
            (nasa_raw_dir / "discovery_fixture.json").write_text("{}", encoding="utf-8")
            (nasa_raw_dir / "mars_page.json").write_text("{}", encoding="utf-8")

            _save_source_state(
                "nasa",
                visited_urls=["https://science.nasa.gov/solar-system/"],
                pending_queue=[{"url": "https://science.nasa.gov/mars/", "depth": 1}],
                complete=False,
                raw_root=str(raw_root),
            )
            state = _load_source_state("nasa", raw_root=str(raw_root))
            raw_paths = _source_raw_record_paths("nasa", raw_root=str(raw_root))

        self.assertEqual(state["pending_queue"], [{"url": "https://science.nasa.gov/mars/", "depth": 1}])
        self.assertEqual(state["visited_urls"], ["https://science.nasa.gov/solar-system/"])
        self.assertEqual([path.name for path in raw_paths], ["mars_page.json"])

    def test_ingest_entrypoint_default_limit_is_80(self):
        from scripts import ingest_solar_system_sources as module

        parser = module.argparse.ArgumentParser()
        parser.add_argument("--limit", type=int, default=80)
        args = parser.parse_args([])
        self.assertEqual(args.limit, 80)

    def test_source_cleanup_targets_point_to_source_specific_outputs(self):
        targets = source_cleanup_targets(
            "nasa",
            raw_root="raw_root",
            triples_root="triples_root",
            evaluation_root="eval_root",
            chroma_root="chroma_root",
        )

        self.assertEqual(targets["raw_dir"], os.path.join("raw_root", "nasa"))
        self.assertEqual(targets["triples_dir"], os.path.join("triples_root", "nasa"))
        self.assertEqual(
            targets["evaluation_report"],
            os.path.join("eval_root", "nasa_ingestion_report.json"),
        )
        self.assertEqual(targets["chroma_dir"], os.path.join("chroma_root", "nasa"))

    def test_clear_source_ingestion_outputs_removes_raw_triples_and_report_but_leaves_chroma_to_runtime_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_root = root / "data" / "raw_json"
            triples_root = root / "data" / "triples"
            evaluation_root = root / "evaluation" / "ingestion"
            chroma_root = root / "data" / "chroma_db"

            (raw_root / "nasa").mkdir(parents=True)
            (triples_root / "nasa").mkdir(parents=True)
            evaluation_root.mkdir(parents=True)
            (chroma_root / "nasa").mkdir(parents=True)

            (raw_root / "nasa" / "mars.json").write_text("{}", encoding="utf-8")
            (triples_root / "nasa" / "火星_triples.json").write_text("[]", encoding="utf-8")
            (evaluation_root / "nasa_ingestion_report.json").write_text("{}", encoding="utf-8")
            (chroma_root / "nasa" / "chroma.sqlite3").write_text("", encoding="utf-8")

            report = clear_source_ingestion_outputs(
                "nasa",
                raw_root=str(raw_root),
                triples_root=str(triples_root),
                evaluation_root=str(evaluation_root),
                chroma_root=str(chroma_root),
            )

            self.assertFalse((triples_root / "nasa").exists())
            self.assertFalse((evaluation_root / "nasa_ingestion_report.json").exists())
            self.assertTrue((chroma_root / "nasa").exists())
            self.assertTrue((raw_root / "nasa").exists())
            self.assertEqual(report["source"], "nasa")
            self.assertGreaterEqual(len(report["deleted"]["directories"]), 2)
            self.assertEqual(len(report["deleted"]["files"]), 1)
            self.assertEqual(report["runtime_managed"]["chroma_dir"], str(chroma_root / "nasa"))

    def test_materialize_shadow_namespace_replaces_existing_graph_namespace(self):
        calls = []

        class FakeLoader:
            driver = object()

            def __init__(self, source_name):
                self.source_name = source_name

            def clear_source_namespace(self, source_name):
                calls.append(("clear", source_name))
                return 3

            def load_all_triples(self, triples_dir=None):
                calls.append(("load", triples_dir))
                return 2, 1

            def get_stats(self):
                return {"nodes": 2, "rels": 1}

            def close(self):
                calls.append(("close", self.source_name))

        with patch("scripts.ingest_solar_system_sources.Neo4jLoader", FakeLoader), patch(
            "scripts.ingest_solar_system_sources._can_materialize_chroma",
            return_value=False,
        ):
            graph_written, chroma_written, details, warnings, errors = _materialize_shadow_namespace(
                "nasa",
                "triples/nasa",
            )

        self.assertTrue(graph_written)
        self.assertFalse(chroma_written)
        self.assertEqual(calls[:2], [("clear", "nasa"), ("load", "triples/nasa")])
        self.assertEqual(details["graph"]["cleared_items"], 3)
        self.assertEqual(errors, [])
        self.assertTrue(any("embedding model cache" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()

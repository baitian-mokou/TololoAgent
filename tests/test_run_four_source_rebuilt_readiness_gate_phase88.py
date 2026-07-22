import json
import tempfile
import unittest
from pathlib import Path


class Phase88RebuiltReadinessGateTests(unittest.TestCase):
    def test_four_source_coverage_pass_but_production_stays_false(self):
        from scripts import run_four_source_rebuilt_readiness_gate_phase88 as phase88

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "evaluation" / "four_source_expansion" / "phase87" / "package.json"
            package.parent.mkdir(parents=True)
            items = [
                {"source": "zh_wikipedia", "title": "太阳", "source_url": "https://zh.wikipedia.org/wiki/太阳", "schema_version": "x", "quality_flags": {}, "provenance": {"p": "1"}},
                {"source": "nasa", "title": "Juno", "source_url": "https://science.nasa.gov/mission/juno", "schema_version": "x", "quality_flags": {"metadata_repaired": True}, "provenance": {"phase86_rule": "title_from_existing_excerpt_or_existing_title"}},
                {"source": "esa", "title": "Rosetta", "source_url": "https://www.esa.int/rosetta", "schema_version": "x", "quality_flags": {}, "provenance": {"p": "1"}},
                {"source": "wikidata", "title": "火星", "source_url": "https://www.wikidata.org/wiki/Q111", "entity_id": "Q111", "schema_version": "x", "quality_flags": {}, "provenance": {"p": "1"}},
            ]
            triples = [
                {"source_id": row["source"], "subject": row["title"], "predicate": "SOURCE_URL", "object": row["source_url"], "schema_version": "x", "quality_flags": row["quality_flags"], "provenance": row["provenance"]}
                for row in items
            ]
            narratives = [{"source_id": row["source"], "title": row["title"], "source_url": row["source_url"], "schema_version": "x", "quality_flags": row["quality_flags"], "provenance": row["provenance"]} for row in items]
            package.write_text(
                json.dumps(
                    {
                        "manifest": {"approval_status": "pending_review", "production_ready": False, "items": 4, "triples": 4, "narratives": 4, "source_breakdown": {"zh_wikipedia": 1, "nasa": 1, "esa": 1, "wikidata": 1}, "provenance_hash": "abc"},
                        "package": {"items": items, "triples_preview": triples, "narratives_preview": narratives},
                        "integrity": {"errors": [], "failed_or_unrepaired_included": False},
                        "formal_raw_write": False,
                        "formal_default_triples_write": False,
                        "chroma_write": False,
                        "neo4j_write": False,
                        "active_source": "zh_wikipedia",
                        "registry": {"zh_wikipedia": "active", "nasa": "disabled", "esa": "disabled", "wikidata": "disabled"},
                    }
                ),
                encoding="utf-8",
            )
            report = phase88.build_gate(package_report=package, root=root)
            self.assertTrue(report["package_integrity_pass"])
            self.assertTrue(report["four_source_coverage_pass"])
            self.assertFalse(report["production_ready"])
            self.assertEqual(report["approval_status"], "pending_review")
            self.assertTrue(report["nasa_repair_quality"]["sampled"])
            self.assertFalse((root / "data").exists())

    def test_output_path_restricted(self):
        from scripts import run_four_source_rebuilt_readiness_gate_phase88 as phase88

        self.assertTrue(phase88.output_allowed(phase88.ROOT / "evaluation" / "four_source_expansion" / "phase88" / "x.json"))
        self.assertTrue(phase88.output_allowed(phase88.ROOT / "docs" / "x.md", allow_docs=True))
        self.assertFalse(phase88.output_allowed(phase88.ROOT / "data" / "x.json"))
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(phase88.output_allowed(Path(temp) / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

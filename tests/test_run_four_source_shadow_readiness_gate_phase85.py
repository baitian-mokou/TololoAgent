import json
import tempfile
import unittest
from pathlib import Path


class Phase85ReadinessGateTests(unittest.TestCase):
    def test_nasa_zero_blocks_four_source_coverage_and_production(self):
        from scripts import run_four_source_shadow_readiness_gate_phase85 as phase85

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "evaluation" / "four_source_expansion" / "phase84" / "package.json"
            package.parent.mkdir(parents=True)
            package.write_text(
                json.dumps(
                    {
                        "manifest": {
                            "approval_status": "pending_review",
                            "items": 2,
                            "triples": 2,
                            "narratives": 2,
                            "source_breakdown": {"esa": 1, "wikidata": 1},
                            "provenance_hash": "abc",
                        },
                        "package": {
                            "items": [
                                {"source": "esa", "title": "Rosetta", "source_url": "https://www.esa.int/rosetta", "schema_version": "x", "provenance": {"p": "1"}},
                                {"source": "wikidata", "title": "火星", "entity_id": "Q111", "schema_version": "x", "provenance": {"p": "1"}},
                            ],
                            "triples_preview": [
                                {"source_id": "esa", "subject": "Rosetta", "predicate": "SOURCE_URL", "object": "https://www.esa.int/rosetta", "schema_version": "x", "provenance": {"p": "1"}},
                                {"source_id": "wikidata", "subject": "火星", "predicate": "SOURCE_URL", "object": "https://www.wikidata.org/wiki/Q111", "schema_version": "x", "provenance": {"p": "1"}},
                            ],
                            "narratives_preview": [
                                {"source_id": "esa", "title": "Rosetta", "schema_version": "x", "provenance": {"p": "1"}},
                                {"source_id": "wikidata", "title": "火星", "schema_version": "x", "provenance": {"p": "1"}},
                            ],
                        },
                        "integrity": {"errors": [], "rejected_excluded": True},
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
            report = phase85.build_gate(package_report=package, root=root)
            self.assertTrue(report["package_integrity_pass"])
            self.assertFalse(report["four_source_coverage_pass"])
            self.assertFalse(report["production_ready"])
            self.assertIn("nasa_coverage_gap", report["blocking_reasons"])
            self.assertFalse((root / "data").exists())

    def test_output_path_restricted(self):
        from scripts import run_four_source_shadow_readiness_gate_phase85 as phase85

        self.assertTrue(phase85.output_allowed(phase85.ROOT / "evaluation" / "four_source_expansion" / "phase85" / "x.json"))
        self.assertTrue(phase85.output_allowed(phase85.ROOT / "docs" / "x.md", allow_docs=True))
        self.assertFalse(phase85.output_allowed(phase85.ROOT / "data" / "x.json"))
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(phase85.output_allowed(Path(temp) / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()

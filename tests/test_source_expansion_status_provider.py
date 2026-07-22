import json
import tempfile
import unittest
from pathlib import Path

from src.source_expansion_status import collect_source_expansion_status
from src.source_control import get_active_source, get_source_status


class SourceExpansionStatusProviderTests(unittest.TestCase):
    def test_collects_counts_from_local_reports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = "nasa"
            triples_dir = root / "data" / "triples" / source
            eval_dir = root / "evaluation" / "source_expansion" / source
            ingestion_dir = root / "evaluation" / "ingestion"
            triples_dir.mkdir(parents=True)
            eval_dir.mkdir(parents=True)
            ingestion_dir.mkdir(parents=True)
            (triples_dir / "summary.json").write_text(
                json.dumps({"triples_written": 3, "narratives_written": 4}),
                encoding="utf-8",
            )
            (eval_dir / f"{source}_report.json").write_text(
                json.dumps({
                    "gates": {"passed": True},
                    "manifest": {"strict_query_count": 8, "exploratory_query_count": 2},
                    "summary": {"exact_accuracy": 1.0},
                }),
                encoding="utf-8",
            )
            (eval_dir / f"{source}_shadow_materialization_report.json").write_text(
                json.dumps({
                    "chroma": {"stats": {"total": 9}},
                    "neo4j": {"loaded_nodes": 1, "loaded_relationships": 2},
                }),
                encoding="utf-8",
            )
            (ingestion_dir / f"{source}_manifest_ingestion_report.json").write_text(
                json.dumps({"fetched_count": 5}),
                encoding="utf-8",
            )
            probe_dir = root / "evaluation" / "source_expansion"
            (probe_dir / "shadow_graph_probe_report.json").write_text(
                json.dumps({
                    "connection": {"ok": True},
                    "sources": {
                        source: {
                            "status": "ok",
                            "node_count": 6,
                            "relationship_count": 7,
                            "relation_type_counts": {"TARGETS": 4, "OPERATED_BY": 3},
                            "sample_edges": [{"subject": "Cassini", "relation": "TARGETS", "object": "Saturn"}],
                            "contract_checks": {"passed": True, "active_source_unchanged": True},
                        }
                    },
                }),
                encoding="utf-8",
            )

            status = collect_source_expansion_status(base_dir=root, sources=[source])[source]

        self.assertEqual(status["raw_count"], 5)
        self.assertEqual(status["triple_count"], 3)
        self.assertEqual(status["narrative_count"], 4)
        self.assertTrue(status["strict_gate_passed"])
        self.assertEqual(status["exploratory_count"], 2)
        self.assertEqual(status["chroma_shadow_count"], 9)
        self.assertEqual(status["neo4j_last_import_relationships"], 2)
        self.assertEqual(status["last_probe_node_count"], 6)
        self.assertEqual(status["last_probe_relationship_count"], 7)
        self.assertEqual(status["last_probe_relation_type_counts"]["TARGETS"], 4)
        self.assertEqual(status["last_probe_sample_edges"][0]["subject"], "Cassini")
        self.assertTrue(status["last_probe_contract_checks"]["passed"])

    def test_missing_reports_fall_back_without_changing_active_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            before = get_active_source()
            status = collect_source_expansion_status(base_dir=Path(temp_dir), sources=["esa"])["esa"]

        self.assertEqual(get_active_source(), before)
        self.assertEqual(status["source_status"], get_source_status("esa"))
        self.assertFalse(status["strict_gate_passed"])
        self.assertEqual(status["raw_count"], 0)


if __name__ == "__main__":
    unittest.main()

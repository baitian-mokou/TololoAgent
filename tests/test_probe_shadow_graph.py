import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probe_shadow_graph.py"


def load_module():
    spec = importlib.util.spec_from_file_location("probe_shadow_graph", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ProbeShadowGraphTests(unittest.TestCase):
    def test_probe_queries_are_read_only(self):
        module = load_module()
        text = "\n".join(module.PROBE_QUERIES.values()).upper()

        self.assertNotIn(" DELETE ", text)
        self.assertNotIn("DETACH", text)
        self.assertNotIn("CREATE ", text)
        self.assertNotIn("MERGE ", text)
        self.assertNotIn(" SET ", text)

    def test_contract_query_stays_inside_requested_source_namespace(self):
        module = load_module()
        contract = module.PROBE_QUERIES["contract"]

        self.assertIn("coalesce(r.source, '') = $source", contract)
        self.assertNotIn("coalesce(r.source, '') <> ''", contract)

    def test_probe_source_from_rows_builds_counts_and_contract(self):
        module = load_module()

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **params):
                source = params["source"]
                if query == module.PROBE_QUERIES["counts"]:
                    return [{"node_count": 2, "relationship_count": 1}]
                if query == module.PROBE_QUERIES["relation_types"]:
                    return [{"relation": "ORBITS", "count": 1}]
                if query == module.PROBE_QUERIES["sample_edges"]:
                    return [{
                        "subject": "火卫二",
                        "relation": "ORBITS",
                        "object": "火星",
                        "source": source,
                        "schema_version": "nasa_shadow_ready_v1",
                        "source_title": "火卫二",
                        "source_url": "https://example.test",
                    }]
                if query == module.PROBE_QUERIES["contract"]:
                    return [{
                        "bad_source_count": 0,
                        "missing_metadata_count": 0,
                        "missing_schema_count": 0,
                    }]
                raise AssertionError(query)

        class FakeDriver:
            def session(self):
                return FakeSession()

        report = module.probe_source(FakeDriver(), "nasa")

        self.assertEqual(report["node_count"], 2)
        self.assertEqual(report["relationship_count"], 1)
        self.assertEqual(report["relation_type_counts"], {"ORBITS": 1})
        self.assertTrue(report["contract_checks"]["passed"])

    def test_connection_failure_is_reported_without_raising(self):
        module = load_module()

        def fail_connect():
            raise RuntimeError("no service")

        report = module.build_probe_report(["nasa"], connect=fail_connect)

        self.assertFalse(report["connection"]["ok"])
        self.assertEqual(report["sources"]["nasa"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()

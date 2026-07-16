import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from src.knowledge_graph.neo4j_loader import Neo4jLoader


class TestNeo4jLoaderGraphCleaning(unittest.TestCase):
    def test_accepts_esa_mission_operator_and_target_relations(self):
        operated_by = Neo4jLoader._clean_graph_triple({
            "subject": "JUICE",
            "relation": "OPERATED_BY",
            "object": "ESA",
            "source": "esa",
            "source_name": "esa",
        })
        mission_target = Neo4jLoader._clean_graph_triple({
            "subject": "Rosetta",
            "relation": "HAS_MISSION_TARGET",
            "object": "彗星",
            "source": "esa",
            "source_name": "esa",
        })

        self.assertIsNotNone(operated_by)
        self.assertEqual(operated_by["relation"], "OPERATED_BY")
        self.assertEqual(operated_by["object"], "ESA")
        self.assertIsNotNone(mission_target)
        self.assertEqual(mission_target["relation"], "HAS_MISSION_TARGET")
        self.assertEqual(mission_target["object"], "彗星")

    def test_relationship_merge_key_includes_source_namespace(self):
        class FakeSession:
            def __init__(self):
                self.calls = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **params):
                self.calls.append((query, params))

        class FakeDriver:
            def __init__(self, session):
                self._session = session

            def session(self):
                return self._session

        with tempfile.TemporaryDirectory() as tmpdir:
            triples_path = Path(tmpdir) / "水星_triples.json"
            triples_path.write_text(json.dumps([{
                "subject": "水星",
                "relation": "HAS_RADIUS",
                "object": "2439.7 km",
                "source": "nasa",
                "source_name": "nasa",
                "source_title": "水星",
                "raw": "Mean radius (km) 半径 2439.7 km",
            }], ensure_ascii=False), encoding="utf-8")

            session = FakeSession()
            loader = object.__new__(Neo4jLoader)
            loader.driver = FakeDriver(session)
            loader.triples_dir = tmpdir

            with contextlib.redirect_stdout(io.StringIO()):
                loader.load_all_triples()

        rel_merges = [query for query, _ in session.calls if "MERGE (a)-[r:HAS_RADIUS" in query]
        self.assertEqual(len(rel_merges), 1)
        self.assertIn("source: $source_name", rel_merges[0])

    def test_resume_skips_completed_triple_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "火卫一_triples.json").write_text(json.dumps([{
                "subject": "火卫一",
                "relation": "ORBITS",
                "object": "火星",
                "source": "wikidata",
                "source_name": "wikidata",
                "source_title": "火卫一",
                "raw": "火卫一绕火星运行",
            }], ensure_ascii=False), encoding="utf-8")
            (root / "火卫二_triples.json").write_text(json.dumps([{
                "subject": "火卫二",
                "relation": "ORBITS",
                "object": "火星",
                "source": "wikidata",
                "source_name": "wikidata",
                "source_title": "火卫二",
                "raw": "火卫二绕火星运行",
            }], ensure_ascii=False), encoding="utf-8")

            first_seen = []
            first_loader = object.__new__(Neo4jLoader)
            first_loader.driver = object()
            first_loader.triples_dir = tmpdir
            first_loader.source_name = "test"

            def fail_on_second_file(triples, created_nodes=None):
                title = triples[0]["source_title"]
                if title == "火卫二":
                    raise RuntimeError("interrupted")
                first_seen.append(title)
                return 2, 1

            first_loader._write_triples_to_neo4j = fail_on_second_file

            with self.assertRaises(RuntimeError):
                with contextlib.redirect_stdout(io.StringIO()):
                    first_loader.load_all_triples(resume=True)
            self.assertEqual(first_seen, ["火卫一"])

            second_seen = []
            second_loader = object.__new__(Neo4jLoader)
            second_loader.driver = object()
            second_loader.triples_dir = tmpdir
            second_loader.source_name = "test"
            second_loader._write_triples_to_neo4j = (
                lambda triples, created_nodes=None: second_seen.append(triples[0]["source_title"]) or (2, 1)
            )

            with contextlib.redirect_stdout(io.StringIO()):
                loaded = second_loader.load_all_triples(resume=True)
            self.assertEqual(loaded, (2, 1))
            self.assertEqual(second_seen, ["火卫二"])


if __name__ == "__main__":
    unittest.main()

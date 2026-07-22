import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_shadow_from_preview.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_shadow_from_preview", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MaterializeShadowFromPreviewTests(unittest.TestCase):
    def test_dry_run_does_not_initialize_chroma_or_neo4j(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            narrative = root / "current_narratives.json"
            triple = root / "current_triples.json"
            narrative.write_text(json.dumps([{"content": "hello world"}]), encoding="utf-8")
            triple.write_text(json.dumps([{"subject": "火星"}]), encoding="utf-8")
            preview = root / "preview.json"
            preview.write_text(
                json.dumps({"source": "nasa", "selected": {"files": [str(narrative), str(triple)]}}),
                encoding="utf-8",
            )

            calls = {"chroma": 0, "neo4j": 0}

            class FakeChroma:
                def __init__(self, *args, **kwargs):
                    calls["chroma"] += 1

            class FakeNeo4j:
                def __init__(self, *args, **kwargs):
                    calls["neo4j"] += 1

            report = module.materialize_from_preview(
                "nasa",
                preview_path=preview,
                dry_run=True,
                chroma_store_cls=FakeChroma,
                neo4j_loader_cls=FakeNeo4j,
            )

        self.assertTrue(report["dry_run"])
        self.assertEqual(report["chroma"]["skipped_reason"], "dry_run")
        self.assertEqual(report["neo4j"]["skipped_reason"], "dry_run")
        self.assertEqual(calls, {"chroma": 0, "neo4j": 0})

    def test_apply_writes_selected_narratives_to_isolated_chroma_path(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow_dir = root / "shadow"
            narrative = root / "current_narratives.json"
            stale = root / "stale_narratives.json"
            narrative.write_text(
                json.dumps([
                    {
                        "chunk_id": "current-1",
                        "content": "Mars has a thin atmosphere.",
                        "page_title": "Mars",
                        "section": "raw_chunk_1",
                        "source_name": "nasa",
                    }
                ]),
                encoding="utf-8",
            )
            stale.write_text(json.dumps([{"chunk_id": "stale-1", "content": "stale"}]), encoding="utf-8")
            preview = root / "preview.json"
            preview.write_text(
                json.dumps({"source": "nasa", "selected": {"files": [str(narrative)]}}),
                encoding="utf-8",
            )
            calls = {}

            class FakeChroma:
                def __init__(self, persist_dir=None, source_name=None):
                    calls["persist_dir"] = str(persist_dir)
                    calls["source_name"] = source_name
                    self.collection = object()

                def initialize(self):
                    calls["initialized"] = True

                def _filter_existing_documents(self, documents, metadatas, ids):
                    return list(documents), list(metadatas), list(ids), 0

                def add_document(self, documents, metadatas=None, ids=None):
                    calls["documents"] = list(documents)
                    calls["ids"] = list(ids)
                    return len(documents)

                def get_stats(self):
                    return {"total": len(calls.get("documents", []))}

                def close(self):
                    calls["closed"] = True

            class FakeNeo4j:
                driver = None

                def __init__(self, *args, **kwargs):
                    pass

                def close(self):
                    pass

            report = module.materialize_from_preview(
                "nasa",
                preview_path=preview,
                dry_run=False,
                shadow_chroma_root=shadow_dir,
                chroma_store_cls=FakeChroma,
                neo4j_loader_cls=FakeNeo4j,
            )

        self.assertEqual(calls["persist_dir"], str(shadow_dir / "nasa"))
        self.assertEqual(calls["source_name"], "nasa")
        self.assertEqual(calls["ids"], ["current-1"])
        self.assertEqual(report["chroma"]["added_narratives"], 1)
        self.assertEqual(report["selected"]["narrative_files"], 1)
        self.assertNotIn("stale", calls["documents"][0])

    def test_neo4j_connection_failure_is_reported_as_skip(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            triple = root / "current_triples.json"
            triple.write_text(json.dumps([{"subject": "火星"}]), encoding="utf-8")
            preview = root / "preview.json"
            preview.write_text(
                json.dumps({"source": "wikidata", "selected": {"files": [str(triple)]}}),
                encoding="utf-8",
            )

            class FakeNeo4j:
                driver = None

                def __init__(self, *args, **kwargs):
                    pass

                def close(self):
                    pass

            report = module.materialize_from_preview(
                "wikidata",
                preview_path=preview,
                dry_run=False,
                chroma_store_cls=None,
                neo4j_loader_cls=FakeNeo4j,
            )

        self.assertEqual(report["neo4j"]["skipped_reason"], "neo4j_skipped_connection_unavailable")


if __name__ == "__main__":
    unittest.main()

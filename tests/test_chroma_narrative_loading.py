import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from src.vector_store.chroma_store import ChromaStore


class ChromaNarrativeLoadingTests(unittest.TestCase):
    def test_add_document_recovers_stale_collection_handle(self):
        added = []

        class StaleCollection:
            def add(self, documents, metadatas, ids, embeddings):
                raise RuntimeError("Error getting collection: Collection [51eea477] does not exist.")

        class FreshCollection:
            def add(self, documents, metadatas, ids, embeddings):
                added.extend(documents)

        class FakeClient:
            def get_collection(self, collection_name):
                return FreshCollection()

        store = object.__new__(ChromaStore)
        store.client = FakeClient()
        store.collection = StaleCollection()
        store._collection_name = "astronomy_narratives"
        store.initialize = lambda: None
        store._encode_texts = lambda documents: [[0.0, 0.1] for _ in documents]

        with contextlib.redirect_stdout(io.StringIO()):
            added_count = store.add_document(["火星质量约为 6.4171e23 kg。"], metadatas=[{}], ids=["mars_mass"])
        self.assertEqual(added_count, 1)
        self.assertEqual(added, ["火星质量约为 6.4171e23 kg。"])

    def test_incremental_load_skips_existing_chunk_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "火星_narratives.json").write_text(
                json.dumps([
                    {
                        "chunk_id": "mars_existing",
                        "page_title": "火星",
                        "content": "火星已有 chunk 不应该在增量导入时再次写入。",
                        "source_name": "wikidata",
                        "source_title": "火星",
                    },
                    {
                        "chunk_id": "mars_new",
                        "page_title": "火星",
                        "content": "火星新增 chunk 应该在增量导入时补写进 Chroma。",
                        "source_name": "wikidata",
                        "source_title": "火星",
                    },
                ], ensure_ascii=False),
                encoding="utf-8",
            )

            added_ids = []
            store = object.__new__(ChromaStore)
            store.source_name = "test"
            store.triples_dir = str(root)
            store.initialize = lambda: None
            store.clear_database = lambda: (_ for _ in ()).throw(AssertionError("incremental import must not clear"))
            store.add_document = lambda documents, metadatas, ids: added_ids.extend(ids) or len(ids)

            class FakeCollection:
                def get(self, ids=None, include=None):
                    existing = [doc_id for doc_id in ids if doc_id == "mars_existing"]
                    return {"ids": existing}

                def count(self):
                    return len(added_ids) + 1

            store.collection = FakeCollection()

            with contextlib.redirect_stdout(io.StringIO()):
                loaded = store.load_all_narratives(str(root), replace_existing=False, resume=True, skip_existing=True)

            self.assertEqual(loaded, 1)
            self.assertEqual(added_ids, ["mars_new"])

    def test_short_authoritative_narratives_are_loaded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "火卫一_narratives.json").write_text(
                json.dumps([{
                    "page_title": "火卫一",
                    "section": "发现",
                    "content": "火卫一 fixture 记录其绕火星运行，并将发现者登记为阿萨夫·霍尔。",
                    "keywords": ["火卫一", "火星"],
                    "source_name": "wikidata",
                    "source_title": "火卫一",
                }], ensure_ascii=False),
                encoding="utf-8",
            )

            added_docs = []
            store = object.__new__(ChromaStore)
            store.triples_dir = str(root)
            store.initialize = lambda: None
            store.clear_database = lambda: 0
            store.add_document = lambda documents, metadatas, ids: added_docs.extend(documents) or len(documents)

            class FakeCollection:
                def count(self):
                    return len(added_docs)

            store.collection = FakeCollection()

            with contextlib.redirect_stdout(io.StringIO()):
                loaded = store.load_all_narratives(str(root), replace_existing=True)
            self.assertEqual(loaded, 1)
            self.assertEqual(added_docs, ["火卫一 fixture 记录其绕火星运行，并将发现者登记为阿萨夫·霍尔。"])

    def test_resume_skips_completed_narrative_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "火卫一_narratives.json").write_text(
                json.dumps([{
                    "page_title": "火卫一",
                    "content": "火卫一 fixture 记录其绕火星运行，并将发现者登记为阿萨夫·霍尔。",
                    "source_name": "wikidata",
                    "source_title": "火卫一",
                }], ensure_ascii=False),
                encoding="utf-8",
            )
            (root / "火卫二_narratives.json").write_text(
                json.dumps([{
                    "page_title": "火卫二",
                    "content": "火卫二 fixture 记录其绕火星运行，并保留可续入测试文本。",
                    "source_name": "wikidata",
                    "source_title": "火卫二",
                }], ensure_ascii=False),
                encoding="utf-8",
            )

            class FakeCollection:
                def __init__(self, docs):
                    self.docs = docs

                def count(self):
                    return len(self.docs)

            first_added = []
            first_store = object.__new__(ChromaStore)
            first_store.source_name = "test"
            first_store.triples_dir = str(root)
            first_store.initialize = lambda: None
            first_store.clear_database = lambda: 0

            def fail_on_second_file(documents, metadatas, ids):
                if documents[0].startswith("火卫二"):
                    raise RuntimeError("interrupted")
                first_added.extend(documents)
                return len(documents)

            first_store.add_document = fail_on_second_file
            first_store.collection = FakeCollection(first_added)

            with contextlib.redirect_stdout(io.StringIO()):
                first_loaded = first_store.load_all_narratives(str(root), replace_existing=True, resume=True)
            self.assertEqual(first_loaded, 1)
            self.assertEqual(first_added, ["火卫一 fixture 记录其绕火星运行，并将发现者登记为阿萨夫·霍尔。"])

            second_added = []
            clears = []
            second_store = object.__new__(ChromaStore)
            second_store.source_name = "test"
            second_store.triples_dir = str(root)
            second_store.initialize = lambda: None
            second_store.clear_database = lambda: clears.append(True) or 0
            second_store.add_document = lambda documents, metadatas, ids: second_added.extend(documents) or len(documents)
            second_store.collection = FakeCollection(second_added)

            with contextlib.redirect_stdout(io.StringIO()):
                second_loaded = second_store.load_all_narratives(str(root), replace_existing=True, resume=True)
            self.assertEqual(second_loaded, 1)
            self.assertEqual(second_added, ["火卫二 fixture 记录其绕火星运行，并保留可续入测试文本。"])
            self.assertEqual(clears, [])


if __name__ == "__main__":
    unittest.main()

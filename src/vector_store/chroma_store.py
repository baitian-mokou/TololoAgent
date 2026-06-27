"""
Chroma 向量库管理器
存储叙事文本 chunks，支持基于 BAAI/bge-m3 的语义检索
"""
import glob
import hashlib
import json
import os
import re
import shutil
import time
from typing import Dict, List, Optional, Sequence, Union

import numpy as np

from config import BASE_DIR, TRIPLES_DIR
from src.nlp.query_analyzer import build_query_context
from src.nlp.text_normalizer import normalize_narrative_record, normalize_to_simplified
from src.source_control import (
    ACTIVE_SOURCE,
    SOURCE_ROLE,
    get_source_namespace_dir,
    get_source_namespace_artifact_path,
    get_source_schema_version,
    normalize_source_filter,
)


class LocalBGEEmbedder:
    """基于 sentence-transformers 的本地 BGE-M3 embedding 封装。"""

    def __init__(self, model_name: str = "BAAI/bge-m3", cache_root: Optional[str] = None):
        self.model_name = model_name
        self.cache_root = cache_root or os.path.join(BASE_DIR, "models", "embedding")
        self.model_dir = os.path.join(self.cache_root, self.model_name.replace("/", "__"))
        self.model = None
        self.device = "cpu"

    def _has_local_model(self) -> bool:
        required_files = ("config.json", "modules.json")
        return os.path.isdir(self.model_dir) and all(
            os.path.exists(os.path.join(self.model_dir, filename))
            for filename in required_files
        )

    def _ensure_local_model(self):
        os.makedirs(self.cache_root, exist_ok=True)
        if self._has_local_model():
            return

        try:
            from huggingface_hub import snapshot_download

            print(f"[Chroma] 正在下载 embedding 模型 {self.model_name} 到 {self.model_dir}")
            snapshot_download(
                repo_id=self.model_name,
                local_dir=self.model_dir,
            )
        except Exception as e:
            raise RuntimeError(
                f"无法下载 embedding 模型 {self.model_name}。"
                f"请检查网络，或先将模型缓存到 {self.model_dir}。原始错误: {e}"
            ) from e

    def _load_model(self):
        if self.model is not None:
            return

        self._ensure_local_model()

        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except Exception as e:
            raise RuntimeError(
                "加载 sentence-transformers 或 torch 失败，"
                "请确认依赖已安装在当前虚拟环境中。"
            ) from e

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            self.model = SentenceTransformer(self.model_dir, device=self.device)
        except Exception as e:
            raise RuntimeError(
                f"加载本地 embedding 模型失败: {self.model_dir}。原始错误: {e}"
            ) from e

    def encode(self, texts: Sequence[str]):
        self._load_model()
        if not texts:
            dim = self.get_sentence_embedding_dimension()
            return np.zeros((0, dim), dtype=np.float32)

        embeddings = self.model.encode(
            list(texts),
            batch_size=16,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def get_sentence_embedding_dimension(self) -> int:
        self._load_model()
        return int(self.model.get_sentence_embedding_dimension())


class ChromaStore:
    """向量库管理器 - 叙事 chunks 的存储和检索"""

    def __init__(self, persist_dir=None, model_name=None, source_name=None):
        self.source_name = str(source_name or ACTIVE_SOURCE).strip() or ACTIVE_SOURCE
        self.persist_dir = persist_dir or get_source_namespace_dir(
            os.path.join(BASE_DIR, "data", "chroma_db"),
            self.source_name,
        )
        self.triples_dir = get_source_namespace_dir(TRIPLES_DIR, self.source_name)
        self.model_name = model_name or "BAAI/bge-m3"
        self.embedding_cache_dir = os.path.join(BASE_DIR, "models", "embedding")
        self.embedding_model = None
        self.embedding_backend = None
        self.collection = None
        self.client = None
        self._narrative_cache = None
        self._known_titles = None
        self._collection_name = "astronomy_narratives" if self.source_name == ACTIVE_SOURCE else f"astronomy_narratives_{self.source_name}"

    def has_persisted_store(self) -> bool:
        return os.path.exists(os.path.join(self.persist_dir, "chroma.sqlite3"))

    def _init_embedding(self):
        """延迟加载嵌入模型。"""
        if self.embedding_model is None:
            self.embedding_model = LocalBGEEmbedder(
                model_name=self.model_name,
                cache_root=self.embedding_cache_dir,
            )
            self.embedding_backend = "sentence_transformers_bge_m3"
            dimension = self.embedding_model.get_sentence_embedding_dimension()
            print(
                f"[Chroma] 使用 BAAI/bge-m3 embedding，向量维度: {dimension}，"
                f"缓存目录: {self.embedding_model.model_dir}"
            )

    @staticmethod
    def _collection_metadata() -> Dict[str, str]:
        return {"hnsw:space": "cosine"}

    @staticmethod
    def _extract_collection_name(collection_item) -> str:
        return getattr(collection_item, "name", str(collection_item))

    def _list_collection_names(self) -> List[str]:
        if self.client is None:
            return []
        try:
            return [
                self._extract_collection_name(item)
                for item in self.client.list_collections()
            ]
        except Exception:
            return []

    @staticmethod
    def _is_hnsw_index_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(
            token in message
            for token in (
                "error loading hnsw index",
                "error creating hnsw segment reader",
                "error constructing hnsw segment reader",
                "hnsw segment reader",
                "backfill request to compactor",
                "error in compaction",
                "failed to apply logs to the hnsw segment writer",
                "hnsw segment writer",
            )
        )

    def _quarantine_persist_dir(self) -> Optional[str]:
        """把损坏的 Chroma 持久化目录隔离出来，便于重新初始化。"""
        if not os.path.isdir(self.persist_dir):
            os.makedirs(self.persist_dir, exist_ok=True)
            return None

        base_dir = os.path.dirname(self.persist_dir)
        name = os.path.basename(self.persist_dir.rstrip("\\/"))
        backup_dir = os.path.join(base_dir, f"{name}.broken.{time.strftime('%Y%m%d_%H%M%S')}")

        try:
            shutil.move(self.persist_dir, backup_dir)
            print(f"[Chroma] 已隔离损坏的持久化目录: {backup_dir}")
        except Exception:
            try:
                shutil.rmtree(self.persist_dir, ignore_errors=False)
                print(f"[Chroma] 已删除损坏的持久化目录: {self.persist_dir}")
            except Exception:
                raise

        os.makedirs(self.persist_dir, exist_ok=True)
        return backup_dir

    def _recover_chroma_store(self, exc: Exception, reason: str):
        """遇到坏索引时，自动重建 Chroma 持久化目录和集合。"""
        if not self._is_hnsw_index_error(exc):
            raise exc

        print(f"[Chroma] 检测到 Chroma HNSW 索引损坏，准备重建: {reason}: {exc}")
        self.client = None
        self.collection = None
        self._quarantine_persist_dir()
        self._init_chroma(force_recover=False)

    def _init_chroma(self, force_recover: bool = True):
        """初始化 Chroma 客户端和集合。"""
        if self.client is None:
            import chromadb

            os.makedirs(self.persist_dir, exist_ok=True)
            collection_name = self._collection_name
            try:
                self.client = chromadb.PersistentClient(path=self.persist_dir)
                try:
                    existing_names = self._list_collection_names()
                    if collection_name in existing_names:
                        self.collection = self.client.get_collection(collection_name)
                        count = self.collection.count()
                        print(f"[Chroma] 已有集合 '{collection_name}'，{count} 条记录")
                    else:
                        self.collection = self.client.create_collection(
                            collection_name,
                            metadata=self._collection_metadata(),
                        )
                        print(f"[Chroma] 创建新集合 '{collection_name}'")
                except Exception as e:
                    if force_recover and self._is_hnsw_index_error(e):
                        self._recover_chroma_store(e, "初始化集合时读取失败")
                        return
                    try:
                        self.collection = self.client.get_collection(collection_name)
                    except Exception:
                        self.collection = self.client.create_collection(
                            collection_name,
                            metadata=self._collection_metadata(),
                        )
                    print(f"[Chroma] 集合 '{collection_name}' 已就绪")
            except Exception as e:
                if force_recover and self._is_hnsw_index_error(e):
                    self._recover_chroma_store(e, "创建 PersistentClient 失败")
                    return
                raise

    def _encode_texts(self, texts: Sequence[str]) -> List[List[float]]:
        self._init_embedding()
        if not texts:
            return []
        normalized = [normalize_to_simplified(str(text or "")).strip() for text in texts]
        embeddings = self.embedding_model.encode(normalized)
        if hasattr(embeddings, "tolist"):
            return embeddings.tolist()
        return embeddings

    def _recreate_collection(self):
        """当历史集合维度不兼容时，重建空集合。"""
        if self.client is None:
            self._init_chroma()
        if self.client is None:
            return

        collection_name = self._collection_name
        try:
            self.client.delete_collection(collection_name)
        except Exception:
            pass

        self.collection = self.client.create_collection(
            collection_name,
            metadata=self._collection_metadata(),
        )
        print("[Chroma] 检测到旧集合向量维度不兼容，已重建空集合")

    def _rebuild_persist_store(self):
        """隔离损坏的持久化目录，并创建一个全新的空集合。"""
        self.client = None
        self.collection = None
        self._quarantine_persist_dir()
        self._init_chroma(force_recover=False)
        print("[Chroma] 已重建持久化目录并创建空集合")

    def _load_narrative_cache(self) -> List[dict]:
        if self._narrative_cache is not None:
            return self._narrative_cache

        cache = []
        for filepath in glob.glob(os.path.join(self.triples_dir, "*_narratives.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    narratives = json.load(f)
            except Exception:
                continue

            for item in narratives:
                record = normalize_narrative_record(item)
                record_source = record.get("source_name") or record.get("source")
                if record_source not in {self.source_name}:
                    continue
                content = normalize_to_simplified(str(record.get("content", "")).strip())
                if len(content) < 40:
                    continue
                keywords = record.get("keywords", [])
                if isinstance(keywords, list):
                    keywords = [normalize_to_simplified(str(term).strip()) for term in keywords if str(term).strip()]
                else:
                    keywords = [normalize_to_simplified(str(keywords).strip())] if str(keywords).strip() else []
                source_name = normalize_to_simplified(str(record_source or "").strip()) or self.source_name
                source_title = normalize_to_simplified(str(record.get("source_title", "")).strip()) or record.get("page_title", "")
                cache.append({
                    "chunk_id": record.get("chunk_id", ""),
                    "page_title": normalize_to_simplified(str(record.get("page_title", "")).strip()),
                    "section": normalize_to_simplified(str(record.get("section", "")).strip()),
                    "keywords_list": keywords,
                    "keywords": ",".join(keywords),
                    "content": content,
                    "source_name": source_name,
                    "source_role": normalize_to_simplified(str(record.get("source_role", SOURCE_ROLE)).strip()) or SOURCE_ROLE,
                    "source_title": source_title,
                    "origin": normalize_to_simplified(str(record.get("origin", "")).strip()),
                    "type": normalize_to_simplified(str(record.get("type", "")).strip()),
                    "schema_version": normalize_to_simplified(str(record.get("schema_version", "")).strip()),
                })

        self._narrative_cache = cache
        self._known_titles = sorted({item["page_title"] for item in cache if item["page_title"]}, key=len, reverse=True)
        return self._narrative_cache

    @staticmethod
    def _clean_query_for_topics(query: str, primary_entity: str) -> str:
        text = normalize_to_simplified(str(query or "")).strip()
        for token in ("为什么", "为何", "怎么", "如何", "请问", "一下", "谁", "是什么", "是啥", "吗", "呢"):
            text = text.replace(token, " ")
        if primary_entity:
            text = text.replace(primary_entity, " ")
        return re.sub(r"\s+", " ", text).strip()

    def _extract_query_context(self, query: str) -> dict:
        self._load_narrative_cache()
        alias_map = {
            "月亮": "月球",
            "红色星球": "火星",
            "pluto": "冥王星",
            "mars": "火星",
            "moon": "月球",
        }
        return build_query_context(
            query,
            known_titles=self._known_titles or [],
            alias_map=alias_map,
            max_topic_terms=6,
        )

    @staticmethod
    def _content_excerpt(text: str, limit: int = 200) -> str:
        return text[:limit] + "..." if len(text) > limit else text

    @staticmethod
    def _topic_hits(text: str, terms: Sequence[str], hit_score: int) -> int:
        score = 0
        for term in terms:
            if term and term in text:
                score += hit_score
        return score

    def _score_narrative_candidate(self, candidate: dict, query_context: dict, vector_score: float = 0.0) -> float:
        page_title = candidate.get("page_title", "")
        section = candidate.get("section", "")
        keywords = candidate.get("keywords", "")
        content = candidate.get("content", "")
        primary = query_context.get("primary_entity", "")
        entities = [normalize_to_simplified(str(item)).strip() for item in query_context.get("entities", []) if str(item).strip()]
        topic_terms = query_context.get("topic_terms", [])
        query = query_context.get("query", "")
        relation_hints = query_context.get("relation_hints", [])

        if "negative_absence" in query_context.get("topic_intents", []):
            return -1.0

        score = vector_score * 40.0
        strict_entity_narrative = primary and any(hint in relation_hints for hint in ("HAS_ATMOSPHERE", "HAS_RADIUS", "HAS_MASS"))
        if entities:
            if page_title == primary:
                score += 120
            elif page_title in entities:
                score += 95
            elif primary and primary in page_title:
                score += 70
            elif any(entity and entity in page_title for entity in entities):
                score += 55
            elif strict_entity_narrative:
                return -1.0
            elif any(entity and entity in content for entity in entities):
                score += 30
            else:
                score -= 95
        elif primary:
            if page_title == primary:
                score += 120
            elif primary in page_title:
                score += 70
            elif primary in content:
                score += 30
            else:
                score -= 95

        score += self._topic_hits(section, topic_terms, 26)
        score += self._topic_hits(keywords, topic_terms, 18)
        score += self._topic_hits(content, topic_terms, 12)

        for entity in entities[:3]:
            if entity and entity in content:
                score += 10 if entity != primary else 14
        if "为什么" in query or "为何" in query:
            if any(token in content for token in ("因为", "由于", "因此", "导致", "使得", "所以")):
                score += 12
        if "成分" in query and any(token in content for token in ("二氧化碳", "氮气", "氩气", "%")):
            score += 14
        if "稀薄" in query and any(token in content for token in ("稀薄", "较薄", "气压", "太阳风")):
            score += 14
        score += self._score_solar_luminosity_narrative(section, keywords, content, query_context)

        return score

    @staticmethod
    def _score_solar_luminosity_narrative(section: str, keywords: str, content: str, query_context: dict) -> int:
        if "solar_luminosity" not in query_context.get("topic_intents", []):
            return 0
        text = f"{section} {keywords} {content}"
        has_fusion = any(token in text for token in ("核融合", "核反应", "氢融合", "融合反应"))
        has_energy = any(token in text for token in ("能量", "能量来源", "释放能量", "辐射能"))

        bonus = 0
        if has_fusion and has_energy:
            bonus += 80
        if section.startswith("核心"):
            bonus += 36
        elif section == "概要" and has_fusion:
            bonus += 30
        if "能量来源" in text:
            bonus += 20
        return bonus

    def _preselect_narrative(self, item: dict, query_context: dict) -> bool:
        primary = query_context.get("primary_entity", "")
        entities = [normalize_to_simplified(str(item)).strip() for item in query_context.get("entities", []) if str(item).strip()]
        topic_terms = query_context.get("topic_terms", [])
        page_title = item.get("page_title", "")
        section = item.get("section", "")
        keywords = item.get("keywords", "")
        content = item.get("content", "")

        if primary and page_title == primary:
            return True
        if entities and any(entity and entity in page_title for entity in entities):
            return True
        if entities and any(entity and entity in content for entity in entities) and any(term in section or term in keywords or term in content for term in topic_terms):
            return True
        if primary and primary in content and any(term in section or term in keywords or term in content for term in topic_terms):
            return True
        if any(term in section or term in keywords for term in topic_terms):
            return True
        return False

    def _merge_candidates(self, vector_candidates: Sequence[dict], local_candidates: Sequence[dict]) -> List[dict]:
        merged = {}
        for item in list(vector_candidates) + list(local_candidates):
            key = item.get("chunk_id") or f"{item.get('page_title', '')}::{item.get('section', '')}::{item.get('content', '')[:80]}"
            current = merged.get(key)
            if current is None:
                merged[key] = dict(item)
                continue
            current["vector_score"] = max(current.get("vector_score", 0.0), item.get("vector_score", 0.0))
            for field in (
                "page_title", "section", "keywords", "content", "chunk_id",
                "source_name", "source_title", "origin", "type", "schema_version",
            ):
                if not current.get(field) and item.get(field):
                    current[field] = item[field]
        return list(merged.values())

    def _extract_source_metadata(self, meta: dict, page_title: str) -> dict:
        source_name = normalize_to_simplified(str(meta.get("source_name") or meta.get("source", "")).strip())
        source_title = normalize_to_simplified(str(meta.get("source_title", "")).strip())
        normalized_page_title = normalize_to_simplified(str(page_title or "").strip())

        if not source_title:
            source_title = normalized_page_title

        if not source_name:
            source_name = self.source_name

        return {
            "source_name": source_name,
            "source_title": source_title,
            "source_role": normalize_to_simplified(str(meta.get("source_role", SOURCE_ROLE)).strip()) or SOURCE_ROLE,
            "origin": normalize_to_simplified(str(meta.get("origin", "")).strip()),
            "type": normalize_to_simplified(str(meta.get("type", "")).strip()),
            "schema_version": get_source_schema_version(source_name),
        }

    def initialize(self):
        """兼容接口：初始化 embedding 模型与 Chroma 集合。"""
        self._init_embedding()
        self._init_chroma()
        return self

    def add_document(
        self,
        documents: Union[str, Sequence[str]],
        metadatas: Optional[Sequence[dict]] = None,
        ids: Optional[Sequence[str]] = None,
    ) -> int:
        """兼容接口：向 Chroma 添加一个或多个文档。"""
        self.initialize()

        if isinstance(documents, str):
            documents = [documents]
        else:
            documents = [str(doc or "") for doc in documents]

        if not documents:
            return 0

        if metadatas is None:
            metadatas = [{} for _ in documents]
        else:
            metadatas = list(metadatas)

        if ids is None:
            ids = [
                hashlib.md5(doc.encode("utf-8")).hexdigest()[:12]
                for doc in documents
            ]
        else:
            ids = [str(doc_id) for doc_id in ids]

        embeddings = self._encode_texts(documents)
        try:
            self.collection.add(
                documents=documents,
                metadatas=list(metadatas),
                ids=list(ids),
                embeddings=embeddings,
            )
            return len(documents)
        except Exception as e:
            if self._is_hnsw_index_error(e):
                self._recover_chroma_store(e, "添加文档时写入失败")
                self.collection.add(
                    documents=documents,
                    metadatas=list(metadatas),
                    ids=list(ids),
                    embeddings=embeddings,
                )
                return len(documents)
            raise

    def delete(self, ids=None, where=None, where_document=None):
        """兼容接口：删除文档。"""
        self._init_chroma()
        if self.collection is None:
            return 0

        try:
            self.collection.delete(ids=ids, where=where, where_document=where_document)
            return 1
        except Exception as e:
            if self._is_hnsw_index_error(e):
                self._recover_chroma_store(e, "删除文档时读取失败")
                self.collection.delete(ids=ids, where=where, where_document=where_document)
                return 1
            raise

    def load_all_narratives(self, narratives_dir=None, replace_existing: bool = False):
        """加载所有叙事 JSON 文件到 Chroma。"""
        try:
            self.initialize()
        except Exception as e:
            if self._is_hnsw_index_error(e):
                self._recover_chroma_store(e, "加载叙事集合失败")
                self.initialize()
            else:
                raise

        narratives_dir = narratives_dir or self.triples_dir
        if replace_existing:
            removed = self.clear_database()
            print(f"[Chroma] 对齐当前 canonical narratives，已清理旧集合 {removed} 条记录")
        nar_files = glob.glob(os.path.join(narratives_dir, "*_narratives.json"))
        print(f"[Chroma] 发现 {len(nar_files)} 个叙事文件")

        total_added = 0
        total_skipped = 0

        for filepath in nar_files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    narratives = json.load(f)
            except Exception:
                continue

            if not narratives:
                continue

            texts = []
            metadatas = []
            ids = []

            for nar in narratives:
                nar = normalize_narrative_record(nar)
                content = nar.get("content", "")
                if not content or len(content) < 50:
                    continue

                chunk_id = nar.get("chunk_id", "")
                if not chunk_id:
                    chunk_id = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]

                texts.append(content)
                metadatas.append({
                    "page_title": nar.get("page_title", ""),
                    "section": nar.get("section", ""),
                    "keywords": ",".join(nar.get("keywords", []))
                    if isinstance(nar.get("keywords", []), list)
                    else normalize_to_simplified(nar.get("keywords", "")),
                    "source": nar.get("source_name") or nar.get("source", ""),
                    "source_name": nar.get("source_name", ""),
                    "source_title": nar.get("source_title", ""),
                    "origin": nar.get("origin", ""),
                    "type": nar.get("type", ""),
                    "source_role": nar.get("source_role", SOURCE_ROLE),
                    "schema_version": nar.get("schema_version", ""),
                })
                ids.append(chunk_id)

            if texts:
                try:
                    batch_size = 50
                    for i in range(0, len(texts), batch_size):
                        batch_texts = texts[i:i + batch_size]
                        batch_metadatas = metadatas[i:i + batch_size]
                        batch_ids = ids[i:i + batch_size]
                        added = self.add_document(
                            documents=batch_texts,
                            metadatas=batch_metadatas,
                            ids=batch_ids,
                        )
                        total_added += added
                except Exception as e:
                    if "dimension" in str(e).lower():
                        print(f"  [Chroma] 旧集合维度不兼容，准备重建后重试: {e}")
                        self._recreate_collection()
                        total_added = 0
                        total_skipped = 0
                        return self.load_all_narratives(
                            narratives_dir=narratives_dir,
                            replace_existing=replace_existing,
                        )
                    if self._is_hnsw_index_error(e):
                        print(f"  [Chroma] 检测到持久化索引异常，准备隔离后全量重试: {e}")
                        self._rebuild_persist_store()
                        total_added = 0
                        total_skipped = 0
                        return self.load_all_narratives(
                            narratives_dir=narratives_dir,
                            replace_existing=False,
                        )
                    print(f"  添加失败: {e}")
                    total_skipped += len(texts)

            fname = os.path.basename(filepath)
            print(f"[Chroma] {fname}: +{len(texts)} 条 (跳过{total_skipped})")

        count = self.collection.count()
        print(f"\n[Chroma] 导入完成！集合总计 {count} 条记录")
        return total_added

    def repair_collection_alignment(self, narratives_dir=None):
        """按当前 canonical narratives 原位重载集合，清理历史残留条目。"""
        before = self.get_stats().get("total", 0)
        added = self.load_all_narratives(narratives_dir=narratives_dir, replace_existing=True)
        after = self.get_stats().get("total", 0)
        return {
            "previous_total": before,
            "reloaded_records": added,
            "current_total": after,
        }

    def clear_database(self):
        """清空 Chroma 向量集合并重新创建空集合。"""
        try:
            self._init_chroma()
        except Exception as e:
            if self._is_hnsw_index_error(e):
                self._recover_chroma_store(e, "清空数据库时初始化失败")
            else:
                raise
        if self.client is None:
            return 0

        collection_name = self._collection_name
        old_count = 0
        try:
            if self.collection is not None:
                old_count = self.collection.count()
        except Exception:
            old_count = 0

        try:
            existing_names = self._list_collection_names()
            if collection_name in existing_names:
                self.client.delete_collection(collection_name)
        except Exception:
            try:
                self.client.delete_collection(collection_name)
            except Exception:
                pass

        self.collection = self.client.create_collection(
            collection_name,
            metadata=self._collection_metadata(),
        )
        print(f"[Chroma] 已清空集合 '{collection_name}'，删除 {old_count} 条记录")
        return old_count

    def search(self, query, top_k=5, query_context: Optional[dict] = None, source_filter: Optional[List[str]] = None):
        """向量召回 + 元数据二阶段重排。"""
        query = normalize_to_simplified(str(query or "")).strip()
        query_context = query_context or self._extract_query_context(query)
        source_filter = normalize_source_filter(source_filter, fallback_source=self.source_name)
        self._load_narrative_cache()

        vector_candidates = []
        try:
            self.initialize()
            collection_count = self.collection.count() if self.collection is not None else 0
        except Exception as e:
            if self._is_hnsw_index_error(e):
                self._recover_chroma_store(e, "搜索前初始化失败")
                collection_count = self.collection.count() if self.collection is not None else 0
            else:
                collection_count = 0

        if collection_count > 0:
            query_embeddings = self._encode_texts([query])
            candidate_k = min(max(top_k * 15, 60), collection_count)
            try:
                results = self.collection.query(
                    query_embeddings=query_embeddings,
                    n_results=candidate_k,
                )
            except Exception as e:
                if "dimension" in str(e).lower():
                    print(f"[Chroma] 查询时发现旧集合维度不兼容: {e}")
                    results = {}
                elif self._is_hnsw_index_error(e):
                    self._recover_chroma_store(e, "搜索时读取索引失败")
                    results = {}
                else:
                    raise

            documents = results.get("documents", [[]])[0] if results else []
            metadatas = results.get("metadatas", [[]])[0] if results else []
            distances = results.get("distances", [[]])[0] if results else []
            ids = results.get("ids", [[]])[0] if results else []

            for doc, meta, dist, doc_id in zip(
                documents,
                metadatas or [{}] * len(documents),
                distances or [0.0] * len(documents),
                ids or [""] * len(documents),
            ):
                page_title = normalize_to_simplified(str(meta.get("page_title", "")).strip())
                source_meta = self._extract_source_metadata(meta or {}, page_title)
                if source_meta["source_name"] not in source_filter:
                    continue
                vector_score = max(0.0, 1.0 - float(dist) / 2.0)
                vector_candidates.append({
                    "chunk_id": doc_id,
                    "page_title": page_title,
                    "section": normalize_to_simplified(str(meta.get("section", "")).strip()),
                    "keywords": normalize_to_simplified(str(meta.get("keywords", "")).strip()),
                    "content": normalize_to_simplified(str(doc or "").strip()),
                    "source_name": source_meta["source_name"],
                    "source_title": source_meta["source_title"],
                    "source_role": source_meta["source_role"],
                    "origin": source_meta["origin"],
                    "type": source_meta["type"],
                    "schema_version": source_meta["schema_version"],
                    "vector_score": vector_score,
                })

        local_candidates = []
        for item in self._narrative_cache or []:
            if item.get("source_name") not in source_filter:
                continue
            if not self._preselect_narrative(item, query_context):
                continue
            local_candidates.append({
                "chunk_id": item.get("chunk_id", ""),
                "page_title": item.get("page_title", ""),
                "section": item.get("section", ""),
                "keywords": item.get("keywords", ""),
                "content": item.get("content", ""),
                "source_name": item.get("source_name", ""),
                "source_title": item.get("source_title", ""),
                "source_role": SOURCE_ROLE,
                "origin": item.get("origin", ""),
                "type": item.get("type", ""),
                "schema_version": get_source_schema_version(item.get("source_name") or self.source_name),
                "vector_score": 0.0,
            })

        merged = self._merge_candidates(vector_candidates, local_candidates)
        ranked = []
        threshold = 70.0 if query_context.get("primary_entity") else 35.0
        for item in merged:
            rerank_score = self._score_narrative_candidate(item, query_context, item.get("vector_score", 0.0))
            if rerank_score < threshold:
                continue
            ranked.append({
                "content": self._content_excerpt(item.get("content", "")),
                "score": min(1.0, max(0.0, rerank_score / 180.0)),
                "page_title": item.get("page_title", ""),
                "section": item.get("section", ""),
                "keywords": item.get("keywords", ""),
                "chunk_id": item.get("chunk_id", ""),
                "source": item.get("source_name", self.source_name),
                "source_name": item.get("source_name", ""),
                "source_title": item.get("source_title", ""),
                "source_role": item.get("source_role", SOURCE_ROLE),
                "origin": item.get("origin", ""),
                "schema_version": get_source_schema_version(item.get("source_name") or self.source_name),
                "_rerank_score": rerank_score,
            })

        ranked.sort(key=lambda item: item["_rerank_score"], reverse=True)
        output = []
        for index, item in enumerate(ranked[:top_k], start=1):
            item["rank"] = index
            item.pop("_rerank_score", None)
            output.append(item)
        return output

    def get_stats(self):
        """获取 Chroma 统计信息。"""
        if self.collection is None:
            self._init_chroma()

        if self.collection is None:
            return {"total": 0, "collections": []}

        try:
            total = self.collection.count()
        except Exception as e:
            if self._is_hnsw_index_error(e):
                self._recover_chroma_store(e, "统计集合信息失败")
                total = self.collection.count() if self.collection is not None else 0
            else:
                raise

        return {
            "total": total,
            "collections": self._list_collection_names(),
        }

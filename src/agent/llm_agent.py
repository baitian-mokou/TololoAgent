"""
LLM Agent — 基于 Qwen3 的知识增强对话引擎
通过 Ollama API 调用 Qwen3 模型，结合 Neo4j 知识图谱和 Chroma 向量库实现 RAG
"""
import sys
import os
import json
import glob
import re
import urllib.request
import urllib.error
import threading
import logging
from typing import Optional, Callable

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, TRIPLES_DIR
from src.nlp.query_analyzer import build_query_context
from src.nlp.text_normalizer import (
    normalize_narrative_record,
    normalize_to_simplified,
    normalize_triple_record,
)
from src.source_control import (
    ACTIVE_SOURCE,
    ORIGIN_INTERNAL_LINK,
    SOURCE_ROLE,
    get_single_source_baseline_namespace,
    get_source_namespace_dir,
    get_source_schema_version,
    normalize_source_filter,
)

logger = logging.getLogger(__name__)


class LLMAgent:
    """Qwen3 知识增强对话引擎（支持本地Ollama和远程OpenAI兼容API）"""

    PLANET_LOCATION_MAP = {
        "水星": "太阳系",
        "金星": "太阳系",
        "地球": "太阳系",
        "火星": "太阳系",
        "木星": "太阳系",
        "土星": "太阳系",
        "天王星": "太阳系",
        "海王星": "太阳系",
        "冥王星": "太阳系",
        "太阳": "太阳系",
    }

    SATELLITE_HOST_PREFIXES = {
        "火卫": "火星",
        "木卫": "木星",
        "土卫": "土星",
        "天卫": "天王星",
        "海卫": "海王星",
        "冥卫": "冥王星",
    }

    def __init__(self, source_name=None, source_role=None, schema_version=None):
        # settings 缓存，避免每次 chat 都读磁盘
        self._settings_cache = None
        self.source_name = source_name or get_single_source_baseline_namespace() or ACTIVE_SOURCE
        self.source_role = source_role or SOURCE_ROLE
        self.schema_version = schema_version
        self.triples_dir = get_source_namespace_dir(TRIPLES_DIR, self.source_name)
        self._load_settings()
        self._neo4j_loader = None
        self._chroma_store = None
        self._entity_catalog = None

    def _load_settings(self):
        """加载 settings.json 中的LLM配置（带缓存）"""
        from src.gui.settings_manager import SettingsManager
        try:
            sm = SettingsManager()
            data = sm.get_all()
            self._settings_cache = data
        except Exception as e:
            logger.warning("读取 settings.json 失败，回退到默认配置: %s", e)
            data = self._settings_cache or {}

        conn = data.get("connect", {})
        self.base_url = conn.get("ollama_url", OLLAMA_BASE_URL).rstrip('/')
        self.model = conn.get("ollama_model", OLLAMA_MODEL)
        self.timeout = int(conn.get("ollama_timeout", OLLAMA_TIMEOUT))

        # 远程API开关
        llm_src = data.get("llm_source", {})
        self.use_remote_api = llm_src.get("use_remote_api", False)
        self.api_base = llm_src.get("api_base", "").rstrip('/')
        self.remote_model = (
            llm_src.get("remote_model", "").strip()
            or self._default_remote_model(self.api_base)
            or self.model
        )
        self.api_key = llm_src.get("api_key", "")

        # 推理参数
        agent = data.get("agent", {})
        self.temperature = float(agent.get("temperature", 0.7))
        self.top_p = float(agent.get("top_p", 0.9))
        self.max_tokens = int(agent.get("max_tokens", 2048))

        # 系统提示词
        self.system_role = agent.get("system_role",
            "你是一个专业的太阳系天文学知识助手，基于托洛洛太阳系知识图谱系统为用户解答问题。")
        self.retrieval_instruction = agent.get("retrieval_instruction",
            "请根据以下知识图谱检索结果，用中文回答用户的问题。如果检索结果不足以回答问题，请如实说明，不要编造信息。回答应简洁准确，可适当补充天文学常识。")
        self.fallback_response = agent.get("fallback_response",
            "请基于以上知识检索结果回答问题。如果知识库中没有相关信息，请说'知识库中暂无相关信息'，然后你可以基于你的常识补充说明。")

    # ─── 可用性检测 ────────────────────────────────────────

    @staticmethod
    def _default_remote_model(api_base: str) -> str:
        if "deepseek" in str(api_base or "").lower():
            return "deepseek-v4-flash"
        return ""

    @staticmethod
    def _normalize_model_name(name: str) -> str:
        name = str(name or "").strip().lower()
        if name.endswith(":latest"):
            name = name[:-7]
        return name

    @classmethod
    def _model_names_match(cls, requested: str, available: str) -> bool:
        requested = cls._normalize_model_name(requested)
        available = cls._normalize_model_name(available)
        return bool(requested and available and requested == available)

    def is_ollama_running(self) -> bool:
        """检测 Ollama 服务是否运行"""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def is_model_available(self) -> bool:
        """检测 Qwen3 模型是否已下载"""
        models = self.get_available_models()
        if any(self._model_names_match(self.model, name) for name in models):
            return True

        # Some Ollama setups can load a configured model via /api/chat even when
        # the tag list is stale or incomplete. /api/show is a closer availability
        # probe for the exact model name used by chat.
        try:
            payload = json.dumps({"model": self.model}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/show",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
                return True
        except Exception:
            return False

    def get_available_models(self) -> list:
        """获取已下载的模型列表"""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                names = []
                for item in data.get("models", []):
                    for key in ("name", "model"):
                        name = item.get(key)
                        if name and name not in names:
                            names.append(name)
                return names
        except Exception:
            return []

    # ─── 知识检索 ────────────────────────────────────────

    def _get_neo4j_loader(self):
        """懒加载 Neo4jLoader"""
        if self._neo4j_loader is None:
            try:
                from src.knowledge_graph.neo4j_loader import Neo4jLoader
                self._neo4j_loader = Neo4jLoader(source_name=self.source_name)
            except Exception as e:
                logger.warning("Neo4jLoader 初始化失败: %s", e)
                return None
        return self._neo4j_loader

    def _get_chroma_store(self):
        """懒加载 ChromaStore"""
        if self._chroma_store is None:
            try:
                from src.vector_store.chroma_store import ChromaStore
                self._chroma_store = ChromaStore(source_name=self.source_name)
            except Exception as e:
                logger.warning("ChromaStore 初始化失败: %s", e)
                return None
        return self._chroma_store

    @staticmethod
    def _normalize_entity_name(name: str) -> str:
        value = normalize_to_simplified(str(name or "")).strip()
        value = re.sub(r"_+", "_", value)
        if "#" in value:
            value = value.split("#", 1)[0].strip()
        value = re.sub(r"\s+", " ", value)
        return value

    def _get_entity_catalog(self) -> list:
        if self._entity_catalog is not None:
            return self._entity_catalog

        entities = set()
        for path in glob.glob(os.path.join(self.triples_dir, "*.json")):
            base = os.path.basename(path)
            for suffix in ("_triples.json", "_narratives.json"):
                if base.endswith(suffix):
                    entity = self._normalize_entity_name(base[:-len(suffix)])
                    if entity:
                        entities.add(entity)
        self._entity_catalog = sorted(entities, key=len, reverse=True)
        return self._entity_catalog

    def _extract_query_context(self, query: str) -> dict:
        alias_map = {
            "月亮": "月球",
            "red planet": "火星",
            "mars": "火星",
            "moon": "月球",
            "pluto": "冥王星",
        }
        return build_query_context(
            query,
            known_titles=self._get_entity_catalog(),
            alias_map=alias_map,
            max_topic_terms=8,
        )

    @staticmethod
    def _looks_like_explanatory_text(text: str) -> bool:
        value = normalize_to_simplified(str(text or "")).strip()
        if not value:
            return True
        if "\n" in value or len(value) > 60:
            return True
        bad_phrases = (
            "因为", "由于", "因此", "所以", "表示", "意味着", "说明", "推测",
            "可能", "可以", "而且", "但是", "其中", "之后", "目前", "已经",
            "认为", "发现有", "导致", "形成", "存在",
        )
        return any(token in value for token in bad_phrases)

    @classmethod
    def _is_valid_discoverer_name(cls, text: str) -> bool:
        value = normalize_to_simplified(str(text or "")).strip()
        value = value.replace("（ 美国 ）", "").replace("（美国）", "").strip(" ，,.;；。")
        if not value:
            return False
        if re.search(r"\d|年|月|日|天文台|发现日期|罗威尔", value):
            return False
        cleaned = re.sub(r"[·,，、 ]", "", value)
        if len(cleaned) < 2 or len(cleaned) > 30:
            return False
        return not cls._looks_like_explanatory_text(value)

    @classmethod
    def _is_valid_orbit_target(cls, text: str) -> bool:
        value = normalize_to_simplified(str(text or "")).strip()
        if not value or cls._looks_like_explanatory_text(value):
            return False
        if len(value) > 20:
            return False
        if any(token in value for token in ("轨道", "密度", "同步自转", "行星-", "系统", "卫星")):
            return value in {"太阳", "地球", "火星", "木星", "土星", "天王星", "海王星", "冥王星", "月球"}
        return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z·\-]{2,20}", value))

    def _score_local_triple_candidate(self, triple: dict, query_context: dict) -> int:
        from src.knowledge_graph.neo4j_loader import Neo4jLoader

        normalized = normalize_triple_record(triple)
        subject = self._normalize_entity_name(normalized.get("subject", ""))
        relation = normalize_to_simplified(str(normalized.get("relation", "")).strip())
        raw = normalize_to_simplified(str(normalized.get("raw", "")).strip())
        obj = Neo4jLoader._normalize_relation_object(relation, normalized.get("object", ""), raw=raw, subject=subject)
        source_title = self._normalize_entity_name(normalized.get("source_title", ""))
        primary = query_context.get("primary_entity", "")
        entities = [self._normalize_entity_name(item) for item in query_context.get("entities", []) if item]
        topic_terms = query_context.get("topic_terms", [])
        relation_hints = query_context.get("relation_hints", [])
        if "negative_absence" in query_context.get("topic_intents", []):
            return -1

        if relation not in Neo4jLoader.GRAPH_RELATION_WHITELIST:
            return -1
        if not Neo4jLoader._is_valid_subject(subject):
            return -1
        if relation == "DISCOVERED_BY" and not Neo4jLoader._is_valid_discoverer(obj):
            return -1
        if relation == "ORBITS" and not Neo4jLoader._is_valid_orbit_target(obj):
            return -1
        if relation == "IS_A" and not Neo4jLoader._is_valid_type_object(obj):
            return -1
        if relation == "LOCATED_IN" and not Neo4jLoader._is_valid_location_object(obj):
            return -1
        if relation == "PART_OF" and not Neo4jLoader._is_valid_part_of_object(obj):
            return -1
        if relation == "HAS_ATMOSPHERE" and not Neo4jLoader._is_valid_atmosphere_object(obj):
            return -1
        if relation in {"HAS_RADIUS", "HAS_MASS"} and not Neo4jLoader._is_valid_quantity_object(obj, relation):
            return -1

        score = 0
        strict_relation_query = (
            primary
            and len(relation_hints) == 1
            and relation_hints[0] in {"ORBITS", "DISCOVERED_BY", "HAS_ATMOSPHERE", "LOCATED_IN", "PART_OF", "HAS_RADIUS", "HAS_MASS"}
        )

        if strict_relation_query:
            if subject != primary or relation != relation_hints[0]:
                return -1
        elif entities:
            if subject == primary:
                score += 120
            elif subject in entities:
                score += 95
            else:
                return -1
        elif primary:
            if subject == primary:
                score += 120
            else:
                return -1

        if relation_hints:
            if relation in relation_hints:
                score += 70
            else:
                return -1

        for token in topic_terms:
            if not token:
                continue
            if token in subject:
                score += 18
            if token in obj:
                score += 20
            if token in relation:
                score += 24
            if token in source_title or token in raw:
                score += 12

        for entity in entities[:3]:
            if source_title and entity and entity in source_title:
                score += 12 if entity != primary else 18
            if raw and entity and entity in raw:
                score += 8 if entity != primary else 10

        return score

    def _infer_satellite_host(self, entity: str) -> str:
        normalized = self._normalize_entity_name(entity)
        if normalized == "月球":
            return "地球"
        for prefix, host in self.SATELLITE_HOST_PREFIXES.items():
            if normalized.startswith(prefix):
                return host
        return ""

    def _infer_structured_graph_answer(self, query_context: dict) -> list:
        primary = query_context.get("primary_entity", "")
        relation_hints = query_context.get("relation_hints", [])
        if not primary or not relation_hints:
            return []

        if "ORBITS" in relation_hints:
            host = self._infer_satellite_host(primary)
            if host:
                return [{
                    "subject": primary,
                    "relation": "ORBITS",
                    "object": host,
                    "source": ACTIVE_SOURCE,
                    "source_name": ACTIVE_SOURCE,
                    "source_title": primary,
                    "source_role": SOURCE_ROLE,
                    "origin": ORIGIN_INTERNAL_LINK,
                    "schema_version": get_source_schema_version(ACTIVE_SOURCE),
                }]

        if "PART_OF" in relation_hints:
            host = self._infer_satellite_host(primary)
            if host:
                return [{
                    "subject": primary,
                    "relation": "PART_OF",
                    "object": f"{host}系统",
                    "source": ACTIVE_SOURCE,
                    "source_name": ACTIVE_SOURCE,
                    "source_title": primary,
                    "source_role": SOURCE_ROLE,
                    "origin": ORIGIN_INTERNAL_LINK,
                    "schema_version": get_source_schema_version(ACTIVE_SOURCE),
                }]

        if "LOCATED_IN" in relation_hints:
            if primary in self.PLANET_LOCATION_MAP:
                return [{
                    "subject": primary,
                    "relation": "LOCATED_IN",
                    "object": self.PLANET_LOCATION_MAP[primary],
                    "source": ACTIVE_SOURCE,
                    "source_name": ACTIVE_SOURCE,
                    "source_title": primary,
                    "source_role": SOURCE_ROLE,
                    "origin": ORIGIN_INTERNAL_LINK,
                    "schema_version": get_source_schema_version(ACTIVE_SOURCE),
                }]
            host = self._infer_satellite_host(primary)
            if host:
                return [{
                    "subject": primary,
                    "relation": "LOCATED_IN",
                    "object": f"{host}系统",
                    "source": ACTIVE_SOURCE,
                    "source_name": ACTIVE_SOURCE,
                    "source_title": primary,
                    "source_role": SOURCE_ROLE,
                    "origin": ORIGIN_INTERNAL_LINK,
                    "schema_version": get_source_schema_version(ACTIVE_SOURCE),
                }]

        return []

    def _score_local_narrative_candidate(self, narrative: dict, query_context: dict) -> int:
        page_title = self._normalize_entity_name(narrative.get("page_title", ""))
        section = normalize_to_simplified(str(narrative.get("section", "")).strip())
        keywords = narrative.get("keywords", [])
        if isinstance(keywords, list):
            keywords_blob = ",".join(normalize_to_simplified(str(item).strip()) for item in keywords)
        else:
            keywords_blob = normalize_to_simplified(str(keywords or "").strip())
        content = normalize_to_simplified(str(narrative.get("content", "")).strip())
        primary = query_context.get("primary_entity", "")
        entities = [self._normalize_entity_name(item) for item in query_context.get("entities", []) if item]
        topic_terms = query_context.get("topic_terms", [])
        query = query_context.get("query", "")
        relation_hints = query_context.get("relation_hints", [])

        if "negative_absence" in query_context.get("topic_intents", []):
            return -1

        score = 0
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
                return -1
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

        for token in topic_terms:
            if token in section:
                score += 26
            if token in keywords_blob:
                score += 18
            if token in content:
                score += 12

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
        score += self._score_solar_luminosity_narrative(section, keywords_blob, content, query_context)

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

    def search_neo4j(self, query: str, limit=20, source_filter=None) -> list:
        """在 Neo4j 知识图谱中搜索相关关系"""
        trace = self.search_neo4j_trace(query, limit=limit, source_filter=source_filter)
        return trace["final_result"]

    def search_neo4j_trace(self, query: str, limit=20, source_filter=None) -> dict:
        """返回图查询结果、最终结果及最终来源，便于回归验证。"""
        query = normalize_to_simplified(query).strip()
        query_context = self._extract_query_context(query)
        source_filter = normalize_source_filter(source_filter, fallback_source=self.source_name)
        allow_active_source = ACTIVE_SOURCE in source_filter
        loader = self._get_neo4j_loader()
        if not loader or not loader.driver:
            fallback = self._search_local_triples(query, limit, query_context=query_context, source_filter=source_filter)
            inferred = self._infer_structured_graph_answer(query_context) if allow_active_source else []
            final = inferred[:limit] if inferred else fallback
            return {
                "graph_only": [],
                "final_result": final,
                "final_source": "inferred" if inferred else "fallback",
            }
        try:
            records = loader.search_graph(query_context, limit=limit, source_filter=source_filter)
            if records:
                return {
                    "graph_only": records[:limit],
                    "final_result": records[:limit],
                    "final_source": "graph",
                }
            inferred = self._infer_structured_graph_answer(query_context) if allow_active_source else []
            if inferred:
                return {
                    "graph_only": [],
                    "final_result": inferred[:limit],
                    "final_source": "inferred",
                }
            fallback = self._search_local_triples(query, limit, query_context=query_context, source_filter=source_filter)
            return {
                "graph_only": [],
                "final_result": fallback,
                "final_source": "fallback",
            }
        except Exception as e:
            logger.warning("Neo4j 搜索失败: %s", e)
            fallback = self._search_local_triples(query, limit, query_context=query_context, source_filter=source_filter)
            inferred = self._infer_structured_graph_answer(query_context) if allow_active_source else []
            final = inferred[:limit] if inferred else fallback
            return {
                "graph_only": [],
                "final_result": final,
                "final_source": "inferred" if inferred else "fallback",
            }

    def search_chroma(self, query: str, top_k=5, source_filter=None) -> list:
        """在 Chroma 向量库中语义搜索"""
        query = normalize_to_simplified(query).strip()
        query_context = self._extract_query_context(query)
        source_filter = normalize_source_filter(source_filter, fallback_source=self.source_name)
        store = self._get_chroma_store()
        if not store:
            return self._search_local_narratives(query, top_k, query_context=query_context, source_filter=source_filter)
        if hasattr(store, "has_persisted_store") and not store.has_persisted_store():
            return self._search_local_narratives(query, top_k, query_context=query_context, source_filter=source_filter)
        try:
            stats = store.get_stats()
            if stats.get('total', 0) <= 0:
                return self._search_local_narratives(query, top_k, query_context=query_context, source_filter=source_filter)
            results = store.search(query, top_k=top_k, query_context=query_context, source_filter=source_filter)
            return results or self._search_local_narratives(query, top_k, query_context=query_context, source_filter=source_filter)
        except Exception as e:
            logger.warning("Chroma 搜索失败: %s", e)
            return self._search_local_narratives(query, top_k, query_context=query_context, source_filter=source_filter)

    @staticmethod
    def _score_text(query: str, text: str, title: str = '') -> int:
        """简单关键词评分，用于数据库不可用时的本地 JSON fallback。"""
        query = normalize_to_simplified(query)
        text = normalize_to_simplified(text)
        title = normalize_to_simplified(title)
        if not query or not text:
            return 0
        score = 0
        if title == query:
            score += 1000
        elif title and (query in title or title in query):
            score += 300
        if query in text:
            score += 10
        for token in set(query):
            if token.strip() and token in text:
                score += 1
        return score

    def _search_local_triples(self, query: str, limit=20, query_context: dict = None, source_filter=None) -> list:
        """从 data/triples/*_triples.json 兜底检索关系。"""
        from src.knowledge_graph.neo4j_loader import Neo4jLoader

        query_context = query_context or self._extract_query_context(query)
        source_filter = normalize_source_filter(source_filter, fallback_source=self.source_name)
        results = []
        for path in glob.glob(os.path.join(self.triples_dir, '*_triples.json')):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    triples = json.load(f)
            except Exception:
                continue

            page_title = os.path.basename(path)[:-len("_triples.json")]
            candidate_triples = list(triples)
            narrative_records = Neo4jLoader._load_narrative_records(path)
            candidate_triples.extend(Neo4jLoader._derive_supplemental_graph_triples(page_title, narrative_records))

            for triple in candidate_triples:
                normalized = normalize_triple_record(triple)
                resolved_source = normalized.get('source') or normalized.get('source_name') or self.source_name
                if resolved_source not in source_filter:
                    continue
                subject = str(normalized.get('subject', ''))
                relation = str(normalized.get('relation', ''))
                raw = normalize_to_simplified(str(normalized.get('raw', '')).strip())
                obj = Neo4jLoader._normalize_relation_object(relation, normalized.get('object', ''), raw=raw, subject=subject)
                if not obj:
                    obj = str(normalized.get('object', ''))
                source = str(normalized.get('source_title', '')) or subject
                score = self._score_local_triple_candidate(triple, query_context)
                if score < 70:
                    continue
                results.append({
                    'subject': subject,
                    'relation': relation,
                    'object': obj,
                    'source': resolved_source,
                    'source_name': normalized.get('source_name') or resolved_source,
                    'source_title': source,
                    'source_role': normalized.get('source_role', SOURCE_ROLE),
                    'origin': normalized.get('origin', ''),
                    'schema_version': get_source_schema_version(resolved_source),
                    '_score': score,
                })

        results.sort(key=lambda item: item.pop('_score'), reverse=True)
        return results[:limit]

    def _search_local_narratives(self, query: str, top_k=5, query_context: dict = None, source_filter=None) -> list:
        """从 data/triples/*_narratives.json 兜底检索叙事片段。"""
        import glob
        query_context = query_context or self._extract_query_context(query)
        source_filter = normalize_source_filter(source_filter, fallback_source=self.source_name)
        candidates = []
        for path in glob.glob(os.path.join(self.triples_dir, '*_narratives.json')):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    narratives = json.load(f)
            except Exception:
                continue

            for nar in narratives:
                normalized = normalize_narrative_record(nar)
                resolved_source = normalized.get('source') or normalized.get('source_name') or self.source_name
                if resolved_source not in source_filter:
                    continue
                content = str(normalized.get('content', ''))
                page_title = str(normalized.get('page_title', ''))
                section = str(normalized.get('section', ''))
                keywords = normalized.get('keywords', [])
                score = self._score_local_narrative_candidate(normalized, query_context)
                if score < 70:
                    continue
                candidates.append({
                    'content': content[:200] + '...' if len(content) > 200 else content,
                    'score': min(1.0, score / 180.0),
                    'page_title': page_title,
                    'section': section,
                    'keywords': ','.join(keywords) if isinstance(keywords, list) else str(keywords),
                    'source': resolved_source,
                    'source_name': normalized.get('source_name') or resolved_source,
                    'source_title': normalized.get('source_title', page_title),
                    'source_role': normalized.get('source_role', SOURCE_ROLE),
                    'origin': normalized.get('origin', ''),
                    'schema_version': get_source_schema_version(resolved_source),
                    '_score': score,
                })

        candidates.sort(key=lambda item: item.pop('_score'), reverse=True)
        for index, item in enumerate(candidates[:top_k], 1):
            item['rank'] = index
        return candidates[:top_k]

    # ─── 流式响应解析（Ollama NDJSON + SSE 共用） ──────────

    def _stream_ndjson(self, resp, on_token):
        """解析 Ollama NDJSON 流式响应"""
        full_response = ""
        buffer = b""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if line.strip():
                    try:
                        data = json.loads(line.decode('utf-8'))
                        token = data.get("message", {}).get("content", "")
                        if token:
                            full_response += token
                            on_token(token)
                        if data.get("done"):
                            return full_response
                    except json.JSONDecodeError:
                        continue
        return full_response

    def _stream_sse(self, resp, on_token):
        """解析 OpenAI SSE 流式响应"""
        full_response = ""
        buffer = b""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buffer += chunk
            while b"\n\n" in buffer:
                part, buffer = buffer.split(b"\n\n", 1)
                for line in part.split(b"\n"):
                    if line.startswith(b"data: "):
                        data_str = line[6:].decode('utf-8').strip()
                        if data_str == "[DONE]":
                            return full_response
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    full_response += token
                                    on_token(token)
                        except json.JSONDecodeError:
                            continue
        return full_response

    # ─── LLM 对话调用 ────────────────────────────────────────

    def chat(self, user_input: str,
             neo4j_results: list = None,
             chroma_results: list = None,
             history: list = None,
             on_token: Callable[[str], None] = None) -> str:
        """
        调用 LLM 进行对话（自动选择本地Ollama或远程API）
        """
        if history is None:
            history = []

        # 非流式模式无需预加载设置（流式模式下 chat 已缓存 settings）
        self._load_settings()

        # 构造系统提示词
        system_prompt = self._build_system_prompt(neo4j_results, chroma_results)

        # 构造消息列表
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        # 根据设置选择调用方式
        if self.use_remote_api:
            return self._call_remote_api(messages, on_token)
        else:
            return self._call_ollama(messages, on_token)

    @staticmethod
    def _graph_relation_label(relation: str) -> str:
        mapping = {
            "IS_A": "是",
            "PART_OF": "属于",
            "ORBITS": "绕行",
            "LOCATED_IN": "位于",
            "HAS_ATMOSPHERE": "大气成分",
            "DISCOVERED_BY": "发现者",
            "HAS_RADIUS": "半径",
            "HAS_MASS": "质量",
        }
        return mapping.get(str(relation or "").strip(), str(relation or "").strip())

    @classmethod
    def _graph_relation_priority(cls, relation: str) -> int:
        priorities = {
            "HAS_RADIUS": 100,
            "HAS_MASS": 95,
            "PART_OF": 85,
            "ORBITS": 80,
            "HAS_ATMOSPHERE": 70,
            "LOCATED_IN": 60,
            "IS_A": 50,
            "DISCOVERED_BY": 40,
        }
        return priorities.get(str(relation or "").strip(), 0)

    @classmethod
    def _format_graph_fact(cls, record: dict) -> str:
        subject = str(record.get('subject', '')).strip()
        relation = str(record.get('relation', '')).strip()
        obj = str(record.get('object', '')).strip()
        if not subject or not relation or not obj:
            return ''
        templates = {
            'IS_A': f'{subject}是{obj}',
            'PART_OF': f'{subject}属于{obj}',
            'ORBITS': f'{subject}绕{obj}运行',
            'LOCATED_IN': f'{subject}位于{obj}',
            'HAS_ATMOSPHERE': f'{subject}的大气成分包含{obj}',
            'DISCOVERED_BY': f'{subject}由{obj}发现',
            'HAS_RADIUS': f'{subject}的半径为{obj}',
            'HAS_MASS': f'{subject}的质量为{obj}',
        }
        return templates.get(relation, f'{subject} {cls._graph_relation_label(relation)} {obj}')

    @classmethod
    def _select_graph_prompt_facts(cls, records: list, limit: Optional[int] = None) -> list:
        ranked = []
        seen = set()
        for index, record in enumerate(records or []):
            key = (
                str(record.get('subject', '')).strip(),
                str(record.get('relation', '')).strip(),
                str(record.get('object', '')).strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            ranked.append((cls._graph_relation_priority(key[1]), index, record))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected = [item[2] for item in ranked]
        if limit is None:
            return selected
        return selected[:limit]

    def _build_system_prompt(self, neo4j_results: list = None,
                             chroma_results: list = None) -> str:
        """构造更紧凑的检索提示词，减少 Qwen3 在思考阶段的 token 消耗。"""
        parts = [
            self.system_role,
            "回答规则：仅基于检索结果直接回答，不复述检索过程，不展示思考过程。先给结论，最多6句；缺信息就明确说知识库暂无。",
        ]

        if neo4j_results:
            parts.append("图谱要点:")
            for r in self._select_graph_prompt_facts(neo4j_results, limit=None):
                fact = self._format_graph_fact(r)
                if fact:
                    parts.append(f"- {fact}")

        if chroma_results:
            parts.append("语义要点:")
            for r in chroma_results[:2]:
                title = r.get('page_title', '未知')
                section = r.get('section', '')
                content = r.get('content', '')[:120]
                summary = f"[{title}" + (f"/{section}" if section else "") + f"] {content}"
                parts.append(summary)

        parts.append("如果检索结果不足，请明确说明，不要编造。")
        return "\n".join(parts)

    @staticmethod
    def _sanitize_final_answer(text: str) -> str:
        value = normalize_to_simplified(str(text or "")).strip()
        if not value:
            return ""
        if "</think>" in value:
            value = value.split("</think>", 1)[-1].strip()
        for marker in ("写回答：", "写回答:", "最终回答：", "最终回答:", "最终答案：", "最终答案:"):
            if marker in value:
                value = value.split(marker, 1)[-1].strip()
        value = re.split(
            r"\n\s*(检查是否|在输出中|用户说|输出句子|回答大纲|关键点|为了简洁|但要控制在|（这样|\(这样)",
            value,
            maxsplit=1,
        )[0].strip()
        lines = []
        for line in value.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("写回答：", "写回答:", "回答大纲", "关键点", "但要控制在")):
                continue
            lines.append(stripped)
        joined = "\n".join(lines).strip()
        if not joined:
            return ""
        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])\s*", joined) if item.strip()]
        if sentences:
            return "".join(sentences[:6]).strip()
        return joined
    @classmethod
    def _extract_answer_from_thinking(cls, thinking: str) -> str:
        text = normalize_to_simplified(str(thinking or "")).strip()
        if not text:
            return ""
        for marker in ("最终回答：", "最终回答:", "最终答案：", "最终答案:", "精简版：", "精简版:", "草拟回答：", "草拟回答:"):
            if marker in text:
                candidate = text.split(marker)[-1].strip()
                candidate = re.split(r"\n\s*知识库中说|\n\s*但知识库中|\n\s*为了简洁|\n\s*回答大纲", candidate)[0].strip()
                return cls._sanitize_final_answer(candidate)
        return ""

    def _build_concise_retry_messages(self, messages: list) -> list:
        user_message = ""
        for item in reversed(messages):
            if item.get("role") == "user":
                user_message = str(item.get("content", "")).strip()
                break

        context_chunks = []
        for item in messages:
            if item.get("role") != "system":
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("-") or stripped.startswith("[") or stripped.startswith("图谱要点") or stripped.startswith("语义要点"):
                    context_chunks.append(stripped)

        retry_system = "你是太阳系知识助手。不要展示思考过程，只输出最终答案。优先引用检索里的数值和实体名，最多5句。"
        retry_user_parts = []
        if user_message:
            retry_user_parts.append(f"问题：{user_message}")
        if context_chunks:
            retry_user_parts.append("检索要点：")
            retry_user_parts.extend(context_chunks[:8])
        retry_user_parts.append("请直接给最终回答，不要解释你的推理。")
        return [
            {"role": "system", "content": retry_system},
            {"role": "user", "content": "\n".join(retry_user_parts)},
        ]

    def _extract_usable_ollama_content(self, data: dict) -> str:
        message = data.get("message", {}) if isinstance(data, dict) else {}
        content = str(message.get("content", "") or "").strip()
        if content:
            return self._sanitize_final_answer(content)
        thinking = str(message.get("thinking", "") or "").strip()
        return self._extract_answer_from_thinking(thinking)

    def _call_ollama_nonstream(self, messages: list, allow_retry: bool = True) -> str:
        url = f"{self.base_url}/api/chat"
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "num_predict": self.max_tokens,
                "think": False,
            }
        }).encode('utf-8')

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode())

        content = self._extract_usable_ollama_content(data)
        if content:
            return content

        if allow_retry:
            logger.warning("Ollama 非流式正文为空，使用短提示词重试: model=%s", self.model)
            retry_messages = self._build_concise_retry_messages(messages)
            return self._call_ollama_nonstream(retry_messages, allow_retry=False)

        return ""

    def _call_ollama(self, messages: list,
                     on_token: Optional[Callable[[str], None]] = None) -> str:
        """调用本地 Ollama API (支持流式)"""
        url = f"{self.base_url}/api/chat"
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": on_token is not None,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "num_predict": self.max_tokens,
                "think": False,
            }
        }).encode('utf-8')

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            if on_token:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    streamed = self._stream_ndjson(resp, on_token)
                if streamed.strip():
                    return streamed
                logger.warning("Ollama 流式返回为空，回退到非流式重试: model=%s", self.model)
                return self._call_ollama_nonstream(messages)
            else:
                return self._call_ollama_nonstream(messages)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            logger.error("Ollama API HTTP错误 %s: %s", e.code, error_body)
            return f"[错误] Ollama API 返回 {e.code}: {error_body}"
        except urllib.error.URLError as e:
            logger.error("Ollama 连接失败: %s", e.reason)
            return f"[错误] 无法连接到 Ollama 服务 ({e.reason})"
        except Exception as e:
            logger.exception("Ollama 调用异常")
            return f"[错误] {str(e)}"

    def _call_remote_api(self, messages: list,
                         on_token: Optional[Callable[[str], None]] = None) -> str:
        """调用远程 OpenAI 兼容 API (支持流式)"""
        if not self.api_base or not self.api_key:
            return "[错误] 远程API地址或密钥未配置，请在设置中填写。"

        url = f"{self.api_base}/chat/completions"
        payload = json.dumps({
            "model": self.remote_model,
            "messages": messages,
            "stream": on_token is not None,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }).encode('utf-8')

        req = urllib.request.Request(
            url, data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST"
        )

        try:
            if on_token:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return self._stream_sse(resp, on_token)
            else:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode())
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "")
                    return "[错误] API 返回格式异常"
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            logger.error("远程API HTTP错误 %s: %s", e.code, error_body)
            return f"[错误] 远程API返回 {e.code}: {error_body}"
        except urllib.error.URLError as e:
            logger.error("远程API连接失败: %s", e.reason)
            return f"[错误] 无法连接到远程API ({e.reason})"
        except Exception as e:
            logger.exception("远程API调用异常")
            return f"[错误] {str(e)}"

    # ─── 一句话问答（自动检索 + 生成） ──────────────────

    def ask(self, question: str,
            history: list = None,
            on_token: Callable[[str], None] = None) -> dict:
        """
        一键问答：自动执行知识检索 + LLM 生成
        """
        # 并行检索
        neo4j_results = []
        chroma_results = []
        search_errors = []

        def search_neo4j_task():
            nonlocal neo4j_results
            try:
                neo4j_results = self.search_neo4j(question)
            except Exception as e:
                search_errors.append(f"Neo4j检索: {e}")

        def search_chroma_task():
            nonlocal chroma_results
            try:
                chroma_results = self.search_chroma(question)
            except Exception as e:
                search_errors.append(f"Chroma检索: {e}")

        threads = [
            threading.Thread(target=search_neo4j_task, daemon=True),
            threading.Thread(target=search_chroma_task, daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        if search_errors:
            logger.warning("检索告警: %s", "; ".join(search_errors))

        # 调用 LLM
        answer = self.chat(
            user_input=question,
            neo4j_results=neo4j_results,
            chroma_results=chroma_results,
            history=history,
            on_token=on_token,
        )

        return {
            "answer": answer,
            "neo4j_count": len(neo4j_results),
            "chroma_count": len(chroma_results),
        }

    def close(self):
        """释放资源"""
        if self._neo4j_loader:
            try:
                self._neo4j_loader.close()
            except Exception as e:
                logger.warning("Neo4jLoader 关闭异常: %s", e)
            self._neo4j_loader = None
        self._chroma_store = None

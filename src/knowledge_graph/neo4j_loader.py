"""
Neo4j 三元组导入器
读取 data/triples/*_triples.json 的1655个三元组，批量导入Neo4j
"""
import os
import json
import glob
import re
from typing import Dict, List, Optional
from config import BASE_DIR, TRIPLES_DIR, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from src.nlp.text_normalizer import (
    normalize_narrative_record,
    normalize_to_simplified,
    normalize_triple_record,
)
from src.source_control import (
    ACTIVE_SOURCE,
    RECORD_TYPE_TRIPLE_CANDIDATE,
    SOURCE_ROLE,
    apply_record_metadata,
    get_single_source_baseline_namespace,
    get_source_namespace_dir,
    get_source_schema_version,
    normalize_source_filter,
)


class Neo4jLoader:
    """将三元组导入Neo4j图数据库"""

    GRAPH_RELATION_WHITELIST = {
        "DISCOVERED_BY",
        "ORBITS",
        "IS_A",
        "PART_OF",
        "LOCATED_IN",
        "HAS_ATMOSPHERE",
        "HAS_RADIUS",
        "HAS_MASS",
    }

    ENTITY_HINTS = {
        "太阳", "水星", "金星", "地球", "火星", "木星", "土星", "天王星", "海王星",
        "冥王星", "月球", "火卫一", "火卫二", "火星", "谷神星", "阋神星", "鸟神星",
        "妊神星", "太阳系", "木卫一", "木卫二", "木卫三", "木卫四", "土卫六", "海卫一",
    }

    ORBIT_HOST_ENTITIES = {
        "太阳", "水星", "金星", "地球", "火星", "木星", "土星", "天王星", "海王星", "冥王星",
    }

    LOCATION_ENTITIES = {
        "太阳系", "银河系", "本地星系团", "柯伊伯带", "小行星带", "宜居带",
        "低地球轨道", "地球轨道", "地球系统", "木星系统", "火星系统", "土星系统", "天王星系统",
        "海王星系统", "冥王星系统", "伽利略卫星",
    }

    KNOWN_ANCHOR_ENTITIES = (
        "太阳系", "银河系", "本地星系团", "柯伊伯带", "小行星带", "宜居带",
        "低地球轨道", "地球轨道", "地球系统", "木星系统", "火星系统", "土星系统", "天王星系统",
        "海王星系统", "冥王星系统", "伽利略卫星",
        "太阳", "水星", "金星", "地球", "火星", "木星", "土星", "天王星", "海王星",
        "冥王星", "月球", "火卫一", "火卫二", "木卫一", "木卫二", "木卫三", "木卫四",
        "土卫六", "海卫一",
    )

    TYPE_SUFFIXES = (
        "行星", "恒星", "卫星", "天体", "矮行星", "小行星", "彗星", "星系", "星云",
        "巨行星", "类地行星", "气体行星", "冰巨星", "冰巨行星", "主序星", "红矮星",
        "白矮星", "中子星", "黑洞", "卫星星系",
    )

    PART_OF_SUFFIXES = ("系统", "星系", "带", "群", "团", "集合", "卫星", "行列")
    LOCATION_SUFFIXES = ("系", "带", "轨道", "区域", "天文台", "星系团", "云", "层", "圈")
    ATMOSPHERE_TERMS = ("氢", "氦", "氮", "氧", "氩", "甲烷", "氨", "一氧化碳", "二氧化碳", "水气", "水蒸气", "臭氧", "二氧化硫", "稀薄")
    ATMOSPHERE_FORMULAS = {
        "H2", "HE", "N2", "O2", "AR", "CO2", "H2O", "CH4", "NH3", "SO2", "CO",
    }
    RADIUS_ALLOW_TERMS = (
        "平均半径", "平均半徑", "赤道半径", "赤道半徑", "极半径", "極半徑",
        "半径", "半徑", "mean radius", "equatorial radius", "polar radius", "radius",
    )
    RADIUS_REJECT_TERMS = (
        "直径", "直徑", "diameter", "厚度", "长度", "長度", "宽度", "寬度", "高度",
        "距离", "距離", "轨道半径", "軌道半徑", "环半径", "環半徑", "卫星半径", "衛星半徑",
        "核半径", "核半徑",
    )
    MASS_ALLOW_TERMS = ("质量", "質量", "mass", "太阳质量", "地球质量", "月球质量")
    NOISY_PREFIXES = ("与", "由", "在", "关于", "因为", "由于", "但是", "其中", "如果", "而", "并", "则")
    NOISY_PHRASES = (
        "分别", "四部分", "关于", "由前几代", "在中间的", "与海王星的卫星相同",
        "唯一能够", "假设的海王星外行星", "可能是", "目前", "最后", "首先",
    )
    SATELLITE_HOST_PREFIXES = {
        "火卫": "火星",
        "木卫": "木星",
        "土卫": "土星",
        "天卫": "天王星",
        "海卫": "海王星",
        "冥卫": "冥王星",
    }
    SOLAR_SYSTEM_BODIES = ORBIT_HOST_ENTITIES | {"月球"}

    def __init__(self, uri=None, user=None, password=None, source_name=None):
        self.uri = uri or NEO4J_URI
        self.user = user or NEO4J_USER
        self.password = password or NEO4J_PASSWORD
        self.source_name = source_name or get_single_source_baseline_namespace() or ACTIVE_SOURCE
        self.triples_dir = get_source_namespace_dir(TRIPLES_DIR, self.source_name)
        self.driver = None
        self._connect()

    def _connect(self):
        """连接Neo4j"""
        try:
            from neo4j import GraphDatabase
            self.driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
            # 测试连接
            with self.driver.session() as session:
                session.run("RETURN 1")
            print(f"[Neo4j] 连接成功: {self.uri}")
        except Exception as e:
            print(f"[Neo4j] 连接失败: {e}")
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()

    @staticmethod
    def _safe_name(name):
        """统一清洗名称，确保创建节点和关系时一致"""
        if not name:
            return name
        name = normalize_to_simplified(str(name)).strip()
        # 只做最小清洗：单引号转义、全角分号替换
        name = name.replace("'", "\\u0027")
        name = name.replace("；", ";")
        # 限制长度
        if len(name) > 100:
            name = name[:100]
        return name

    @staticmethod
    def _infer_label(subject_name, relation):
        """根据实体名称和关系推断节点标签（返回预定义的标签，防止Cypher注入）"""
        allowed_labels = {
            'Planet', 'Star', 'Nebula', 'Galaxy', 'Asteroid',
            'Comet', 'Satellite', 'DwarfPlanet', 'Mission',
            'CelestialBody', 'Entity', 'Concept', 'PlanetType',
            'OrbitParameter', 'EnvironmentalFeature',
        }
        celestial_keywords = {
            '行星': 'Planet', '星体': 'CelestialBody', '星云': 'Nebula',
            '星系': 'Galaxy', '小行星': 'Asteroid', '彗星': 'Comet',
            '卫星': 'Satellite',
        }
        if relation in ('被探测', '被发现', '探测'):
            return 'Mission'
        for keyword, label in celestial_keywords.items():
            if keyword in subject_name:
                return label
        return 'CelestialBody'

    def clear_database(self):
        """清空数据库（谨慎使用）"""
        if not self.driver:
            return
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("[Neo4j] 数据库已清空")

    @staticmethod
    def _normalize_object_text(value: str) -> str:
        value = normalize_to_simplified(str(value or "")).strip()
        value = re.sub(r"\s+", " ", value)
        value = value.replace("（ 美国 ）", "").replace("（美国）", "")
        value = value.strip(" ，,.;；。")
        return value

    @classmethod
    def _extract_anchor_entity(cls, text: str) -> str:
        normalized = cls._normalize_object_text(text)
        for entity in sorted(cls.KNOWN_ANCHOR_ENTITIES, key=len, reverse=True):
            if entity and entity in normalized:
                return entity
        return ""

    @classmethod
    def _infer_satellite_host(cls, subject: str) -> str:
        normalized = cls._safe_name(subject)
        if normalized == "月球":
            return "地球"
        for prefix, host in cls.SATELLITE_HOST_PREFIXES.items():
            if normalized.startswith(prefix):
                return host
        return ""

    @classmethod
    def _load_narrative_records(cls, triples_path: str) -> List[dict]:
        narrative_path = triples_path.replace("_triples.json", "_narratives.json")
        if not os.path.exists(narrative_path):
            return []
        try:
            with open(narrative_path, "r", encoding="utf-8") as handle:
                narratives = json.load(handle)
        except Exception:
            return []
        records = []
        for item in narratives:
            normalized = normalize_narrative_record(item)
            content = normalize_to_simplified(str(normalized.get("content", "")).strip())
            if content:
                records.append({
                    "content": content,
                    "origin": normalized.get("origin", ""),
                    "source": normalized.get("source", ACTIVE_SOURCE),
                    "source_name": normalized.get("source_name") or normalized.get("source", ACTIVE_SOURCE),
                    "source_role": normalized.get("source_role", SOURCE_ROLE),
                    "schema_version": normalized.get("schema_version", ""),
                    "source_title": normalized.get("source_title", "") or normalized.get("page_title", ""),
                })
        return records

    @classmethod
    def _derive_supplemental_graph_triples(cls, page_title: str, narrative_records: List[dict]) -> List[dict]:
        subject = cls._safe_name(page_title.split("#", 1)[0])
        if not subject or not narrative_records:
            return []

        derived = []
        host = cls._infer_satellite_host(subject)
        for record in narrative_records:
            content = record.get("content", "")
            if host and any(token in content for token in (f"围绕{host}", f"绕行{host}", f"环绕{host}", f"绕着{host}", f"绕著{host}", f"{host}的卫星")):
                derived.append(apply_record_metadata({
                    "subject": subject,
                    "relation": "ORBITS",
                    "object": host,
                    "pattern": "supplemental_narrative",
                    "raw": content,
                }, record.get("origin"), RECORD_TYPE_TRIPLE_CANDIDATE,
                    source_name=record.get("source_name") or record.get("source"),
                    source_role=record.get("source_role"),
                    source_title=record.get("source_title") or subject,
                    extra={"schema_version": record.get("schema_version")} if record.get("schema_version") else None))
                break

        for record in narrative_records:
            content = record.get("content", "")
            if host and any(token in content for token in (f"{host}的卫星", f"木星的伽利略卫星", "伽利略卫星", f"绕行{host}", f"围绕{host}")):
                derived.append(apply_record_metadata({
                    "subject": subject,
                    "relation": "PART_OF",
                    "object": f"{host}系统",
                    "pattern": "supplemental_narrative",
                    "raw": content,
                }, record.get("origin"), RECORD_TYPE_TRIPLE_CANDIDATE,
                    source_name=record.get("source_name") or record.get("source"),
                    source_role=record.get("source_role"),
                    source_title=record.get("source_title") or subject,
                    extra={"schema_version": record.get("schema_version")} if record.get("schema_version") else None))
                break

        for record in narrative_records:
            content = record.get("content", "")
            if subject in cls.SOLAR_SYSTEM_BODIES and "太阳系" in content and any(token in content for token in ("行星", "卫星", "天体")):
                derived.append(apply_record_metadata({
                    "subject": subject,
                    "relation": "LOCATED_IN",
                    "object": "太阳系",
                    "pattern": "supplemental_narrative",
                    "raw": content,
                }, record.get("origin"), RECORD_TYPE_TRIPLE_CANDIDATE,
                    source_name=record.get("source_name") or record.get("source"),
                    source_role=record.get("source_role"),
                    source_title=record.get("source_title") or subject,
                    extra={"schema_version": record.get("schema_version")} if record.get("schema_version") else None))
                break

        for record in narrative_records:
            content = record.get("content", "")
            radius = cls._extract_subject_radius_from_narrative(subject, content)
            if radius:
                derived.append(apply_record_metadata({
                    "subject": subject,
                    "relation": "HAS_RADIUS",
                    "object": radius,
                    "pattern": "supplemental_narrative",
                    "raw": content,
                }, record.get("origin"), RECORD_TYPE_TRIPLE_CANDIDATE,
                    source_name=record.get("source_name") or record.get("source"),
                    source_role=record.get("source_role"),
                    source_title=record.get("source_title") or subject,
                    extra={"schema_version": record.get("schema_version")} if record.get("schema_version") else None))
                break

        for record in narrative_records:
            content = record.get("content", "")
            discoverer = cls._extract_discoverer_from_narrative(subject, content)
            if discoverer:
                derived.append(apply_record_metadata({
                    "subject": subject,
                    "relation": "DISCOVERED_BY",
                    "object": discoverer,
                    "pattern": "supplemental_narrative",
                    "raw": content,
                }, record.get("origin"), RECORD_TYPE_TRIPLE_CANDIDATE,
                    source_name=record.get("source_name") or record.get("source"),
                    source_role=record.get("source_role"),
                    source_title=record.get("source_title") or subject,
                    extra={"schema_version": record.get("schema_version")} if record.get("schema_version") else None))
                break

        unique = {}
        for item in derived:
            key = (item["subject"], item["relation"], item["object"])
            unique[key] = item
        return list(unique.values())

    @classmethod
    def _extract_subject_radius_from_narrative(cls, subject: str, content: str) -> str:
        compact = re.sub(r"\s+", "", normalize_to_simplified(str(content or "")))
        if not compact:
            return ""
        patterns = (
            rf"{re.escape(subject)}的?半径大约是([0-9][0-9,]*(?:\.\d+)?)公里",
            rf"{re.escape(subject)}的?半径为([0-9][0-9,]*(?:\.\d+)?)公里",
            rf"{re.escape(subject)}[^。；，]{0,80}?半径大约是([0-9][0-9,]*(?:\.\d+)?)公里",
            rf"{re.escape(subject)}[^。；，]{0,80}?半径为([0-9][0-9,]*(?:\.\d+)?)公里",
        )
        for pattern in patterns:
            match = re.search(pattern, compact)
            if match:
                return f"{match.group(1)} km"
        return ""

    @classmethod
    def _extract_discoverer_from_narrative(cls, subject: str, content: str) -> str:
        compact = re.sub(r"\s+", "", normalize_to_simplified(str(content or "")))
        if not compact:
            return ""
        patterns = (
            rf"(?:\d{{4}}年)?([\u4e00-\u9fffA-Za-z·\-]{{2,20}}?)发现{re.escape(subject)}",
            rf"{re.escape(subject)}由([\u4e00-\u9fffA-Za-z·\-]{{2,20}}?)发现",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, compact):
                candidate = cls._normalize_object_text(match.group(1))
                candidate = re.sub(r"^\d{4}年", "", candidate)
                if cls._is_valid_discoverer(candidate):
                    return candidate
        return ""

    @classmethod
    def _is_strict_relation_query(cls, query_context: dict) -> bool:
        relation_hints = [item for item in query_context.get("relation_hints", []) if item]
        primary = cls._safe_name(query_context.get("primary_entity", ""))
        if not primary or len(relation_hints) != 1:
            return False
        return relation_hints[0] in {
            "ORBITS", "DISCOVERED_BY", "HAS_ATMOSPHERE",
            "LOCATED_IN", "PART_OF", "HAS_RADIUS", "HAS_MASS",
        }

    @staticmethod
    def _looks_like_explanatory_text(text: str) -> bool:
        if not text:
            return True
        if "\n" in text or len(text) > 60:
            return True
        bad_phrases = (
            "因为", "由于", "因此", "所以", "表示", "意味着", "说明", "推测",
            "可能", "可以", "而且", "但是", "其中", "之后", "目前", "已经",
            "认为", "发现了", "发现有", "导致", "成为", "形成", "存在",
        )
        return any(token in text for token in bad_phrases)

    @classmethod
    def _is_noisy_fragment(cls, text: str) -> bool:
        value = cls._normalize_object_text(text)
        if not value:
            return True
        if any(value.startswith(prefix) for prefix in cls.NOISY_PREFIXES):
            return True
        if any(phrase in value for phrase in cls.NOISY_PHRASES):
            return True
        if "，" in value or "," in value:
            return True
        if cls._looks_like_explanatory_text(value):
            return True
        return False

    @classmethod
    def _is_valid_subject(cls, text: str) -> bool:
        value = cls._safe_name(text)
        if not value:
            return False
        if len(value) < 2 or len(value) > 40:
            return False
        if cls._is_noisy_fragment(value):
            return False
        if value in cls.KNOWN_ANCHOR_ENTITIES or value in cls.ENTITY_HINTS:
            return True
        if "#" in value:
            return False
        return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9·_\-()]{2,40}", value))

    @classmethod
    def _is_valid_discoverer(cls, text: str) -> bool:
        value = cls._normalize_object_text(text)
        if not value:
            return False
        if re.search(r"\d|年|月|日|天文台|发现日期", value):
            return False
        if any(token in value for token in ("没有", "未", "并未", "他们", "人们", "有人")):
            return False
        if any(token in value for token in ("探测器", "望远镜", "任务", "小组", "轨道", "位置", "图像", "方法", "坑", "号")):
            return False
        if value[0] in "为从在由而并与对给向让使将把被因若但且再这那其该此":
            return False
        cleaned = re.sub(r"[·,，、 ]", "", value)
        if len(cleaned) < 2 or len(cleaned) > 30:
            return False
        if re.fullmatch(r"[\u4e00-\u9fff]{2,5}", cleaned):
            if any(char in cleaned for char in "后来为了再这那此他她它们当现已并未所该其而因若但且"):
                return False
        if cls._is_noisy_fragment(value):
            return False
        return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", cleaned))

    @classmethod
    def _is_valid_orbit_target(cls, text: str) -> bool:
        value = cls._normalize_object_text(text)
        if not value:
            return False
        if cls._is_noisy_fragment(value):
            return False
        anchor = cls._extract_anchor_entity(value)
        if anchor:
            return anchor in cls.ORBIT_HOST_ENTITIES
        if any(token in value for token in ("轨道", "密度", "同步自转", "天体", "系统", "卫星", "行星-", "太阳系")):
            return False
        if len(value) > 20:
            return False
        return value in cls.ORBIT_HOST_ENTITIES

    @classmethod
    def _is_valid_type_object(cls, text: str) -> bool:
        value = cls._normalize_object_text(text)
        if not value or cls._is_noisy_fragment(value):
            return False
        if len(value) > 24:
            return False
        if "的" in value or re.search(r"[一二三四五六七八九十0-9]+颗", value):
            return False
        return any(value.endswith(suffix) or suffix in value for suffix in cls.TYPE_SUFFIXES)

    @classmethod
    def _is_valid_location_object(cls, text: str) -> bool:
        value = cls._normalize_object_text(text)
        if not value or cls._is_noisy_fragment(value):
            return False
        if value in ("赤道区域", "同一轨道", "远离太阳系", "其宜居带", "低层大气"):
            return False
        anchor = cls._extract_anchor_entity(value)
        if anchor:
            return anchor in cls.LOCATION_ENTITIES
        if len(value) > 24:
            return False
        if value.endswith("区域") and value not in ("太阳系区域",):
            return False
        return value in cls.LOCATION_ENTITIES or any(value.endswith(suffix) for suffix in cls.LOCATION_SUFFIXES)

    @classmethod
    def _is_valid_part_of_object(cls, text: str) -> bool:
        value = cls._normalize_object_text(text)
        if not value or cls._is_noisy_fragment(value):
            return False
        anchor = cls._extract_anchor_entity(value)
        if anchor and any(anchor.endswith(suffix) for suffix in cls.PART_OF_SUFFIXES):
            return True
        if len(value) > 24 or "的" in value:
            return False
        return any(value.endswith(suffix) for suffix in cls.PART_OF_SUFFIXES)

    @classmethod
    def _is_valid_atmosphere_object(cls, text: str) -> bool:
        value = cls._normalize_object_text(text)
        if not value or cls._is_noisy_fragment(value):
            return False
        if value in ("四部分", "大气层", "组成部分"):
            return False
        if len(value) > 50:
            return False
        formula = value.replace(" ", "").upper()
        if formula in cls.ATMOSPHERE_FORMULAS:
            return True
        return any(term in value for term in cls.ATMOSPHERE_TERMS) or "%" in value

    @classmethod
    def _is_valid_quantity_object(cls, text: str, relation: str) -> bool:
        value = cls._normalize_object_text(text)
        if not value:
            return False
        if "♠" in value or len(value) > 40:
            return False
        if any(token in value for token in ("（", "）", "(", ")", "代表", "地球的", "倍于", "±", "+", "−", "—")):
            return False
        if relation == "HAS_RADIUS":
            if not re.fullmatch(r"\d[\d,]*(?:\.\d+)?\s*(?:km|光年|kpc|AU|天文单位)", value):
                return False
            numeric = cls._parse_canonical_quantity_value(value, relation)
            return numeric is not None and numeric > 0
        if relation == "HAS_MASS":
            if not re.fullmatch(
                r"\d[\d,]*(?:\.\d+)?(?:(?:\s*×\s*10\s*|[eE])[+\-]?\d+)?\s*(?:kg|太阳质量|地球质量|月球质量)",
                value,
            ):
                return False
            numeric = cls._parse_canonical_quantity_value(value, relation)
            return numeric is not None and numeric > 0
        return False

    @staticmethod
    def _strip_extract_markers(text: str) -> str:
        value = normalize_to_simplified(str(text or ""))
        value = re.sub(r"\d{6,}♠\s*", " ", value)
        value = value.replace("（", "(").replace("）", ")")
        value = value.replace("公斤", "kg").replace("千克", "kg").replace("公里", "km")
        value = value.replace("M ☉", "太阳质量").replace("M☉", "太阳质量")
        value = value.replace("M 🜨", "地球质量").replace("M🜨", "地球质量")
        value = value.replace("×10", " × 10 ").replace("x10", " × 10 ").replace("X10", " × 10 ")
        value = re.sub(r"\s+", " ", value)
        return value.strip(" ，,.;；。")

    @staticmethod
    def _normalize_scalar_number(token: str) -> str:
        value = normalize_to_simplified(str(token or "")).strip()
        value = value.replace("−", "-").replace("—", "-")
        value = re.sub(r"[()]", "", value)
        value = re.sub(r"(?<=\d)\s+(?=\d)", "", value)
        value = re.sub(r"\s*\.\s*", ".", value)
        match = re.search(r"\d[\d,]*(?:\.\d+)?", value)
        return match.group(0) if match else ""

    @staticmethod
    def _quantity_context_text(raw: str, pattern: str = "") -> str:
        return normalize_to_simplified(f"{raw or ''} {pattern or ''}").lower()

    @classmethod
    def _has_quantity_semantics(cls, relation: str, raw: str, pattern: str = "") -> bool:
        context = cls._quantity_context_text(raw, pattern)
        if relation == "HAS_RADIUS":
            if any(term.lower() in context for term in cls.RADIUS_REJECT_TERMS):
                return False
            return any(term.lower() in context for term in cls.RADIUS_ALLOW_TERMS)
        if relation == "HAS_MASS":
            return any(term.lower() in context for term in cls.MASS_ALLOW_TERMS)
        return False

    @classmethod
    def _radius_semantic_class(cls, raw: str, pattern: str = "") -> str:
        context = cls._quantity_context_text(raw, pattern)
        if any(term in context for term in ("平均半径", "平均半徑", "mean radius")):
            return "mean"
        if any(term in context for term in ("赤道半径", "赤道半徑", "equatorial radius")):
            return "equatorial"
        if any(term in context for term in ("极半径", "極半徑", "polar radius")):
            return "polar"
        if any(term in context for term in ("半径", "半徑", "radius")):
            return "generic"
        return ""

    @staticmethod
    def _parse_canonical_quantity_value(value: str, relation: str) -> Optional[float]:
        normalized = normalize_to_simplified(str(value or "")).strip()
        if relation == "HAS_MASS":
            sci = re.fullmatch(r"(\d[\d,]*(?:\.\d+)?)\s*×\s*10\s*([+\-]?\d+)\s*(?:kg|太阳质量|地球质量|月球质量)", normalized)
            if sci:
                return float(sci.group(1).replace(",", "")) * (10 ** int(sci.group(2)))
            e_sci = re.fullmatch(r"(\d[\d,]*(?:\.\d+)?)[eE]([+\-]?\d+)\s*(?:kg|太阳质量|地球质量|月球质量)", normalized)
            if e_sci:
                return float(e_sci.group(1).replace(",", "")) * (10 ** int(e_sci.group(2)))
        plain = re.fullmatch(r"(\d[\d,]*(?:\.\d+)?)\s*(?:km|光年|kpc|AU|天文单位|kg|太阳质量|地球质量|月球质量)", normalized)
        if plain:
            return float(plain.group(1).replace(",", ""))
        return None

    @classmethod
    def _extract_canonical_mass(cls, text: str) -> str:
        value = cls._strip_extract_markers(text)
        if not value:
            return ""

        sci_kg = re.search(
            r"\(?\s*([0-9][0-9,.\s]*)\s*(?:±\s*[0-9][0-9,.\s]*)?\s*\)?\s*×\s*10\s*([+\-]?\d+)\s*kg",
            value,
        )
        if sci_kg:
            mantissa = cls._normalize_scalar_number(sci_kg.group(1))
            if mantissa:
                return f"{mantissa} × 10 {sci_kg.group(2)} kg"

        e_sci_kg = re.search(r"([0-9][0-9,]*(?:\.\d+)?)[eE]([+\-]?\d+)\s*kg", value)
        if e_sci_kg:
            mantissa = cls._normalize_scalar_number(e_sci_kg.group(1))
            exponent = e_sci_kg.group(2)
            if mantissa:
                return f"{mantissa}e{exponent} kg"

        plain_kg = re.search(r"\(?\s*([0-9][0-9,.\s]*)\s*(?:±\s*[0-9][0-9,.\s]*)?\s*\)?\s*kg", value)
        if plain_kg:
            scalar = cls._normalize_scalar_number(plain_kg.group(1))
            if scalar:
                return f"{scalar} kg"

        for unit in ("太阳质量", "地球质量", "月球质量"):
            unit_match = re.search(
                rf"([0-9][0-9,]*(?:\.\d+)?)\s*(?:±\s*[0-9][0-9,]*(?:\.\d+)?)?\s*{unit}",
                value,
            )
            if unit_match and not re.search(r"[–-]\s*[0-9]", unit_match.group(0)):
                return f"{unit_match.group(1)} {unit}"

        earth_ratio = re.search(r"([0-9][0-9,]*(?:\.\d+)?)\s*(?:倍于地球|地球质量的)", value)
        if earth_ratio:
            return f"{earth_ratio.group(1)} 地球质量"
        earth_ratio_tail = re.search(r"地球(?:质量)?的\s*([0-9][0-9,]*(?:\.\d+)?)\s*倍", value)
        if earth_ratio_tail:
            return f"{earth_ratio_tail.group(1)} 地球质量"
        moon_ratio_tail = re.search(r"月球(?:质量)?的\s*([0-9][0-9,]*(?:\.\d+)?)\s*倍", value)
        if moon_ratio_tail:
            return f"{moon_ratio_tail.group(1)} 月球质量"

        return ""

    @classmethod
    def _extract_canonical_radius(cls, text: str) -> str:
        value = cls._strip_extract_markers(text)
        if not value:
            return ""

        for unit in ("km", "光年", "kpc", "AU", "天文单位"):
            match = re.search(
                rf"([0-9][0-9,\s]*(?:\s*\.\s*\d+)?)"
                rf"(?:\s*±\s*[0-9][0-9,]*(?:\.\d+)?)?"
                rf"(?:\s*[+\-−]\s*[0-9][0-9,]*(?:\.\d+)?){{0,2}}\s*{unit}",
                value,
            )
            if match:
                number = cls._normalize_scalar_number(match.group(1))
                if number:
                    return f"{number} {unit}"

        return ""

    @classmethod
    def _normalize_relation_object(cls, relation: str, obj: str, raw: str = "", subject: str = "") -> str:
        value = cls._normalize_object_text(obj)
        raw_value = cls._normalize_object_text(raw)
        if relation == "DISCOVERED_BY":
            value = re.sub(r"\s*（[^)]*争议[^)]*）", "", value)
            value = value.replace("（ 法国 ）", "").replace("（ 德国 ）", "").replace("（ 英国 ）", "")
            value = re.sub(r"\s+", " ", value).strip(" ，,.;；。")
            return value
        if relation == "ORBITS":
            if any(token in f"{value} {raw_value}" for token in ("绕", "围绕", "公转", "轨道")):
                anchor = cls._extract_anchor_entity(value) or cls._extract_anchor_entity(raw_value)
                if anchor in cls.ORBIT_HOST_ENTITIES:
                    return anchor
        if relation == "LOCATED_IN":
            if any(token in f"{value} {raw_value}" for token in ("位于", "位在", "处于", "坐落", "位于", "在")):
                anchor = cls._extract_anchor_entity(value) or cls._extract_anchor_entity(raw_value)
                if anchor in cls.LOCATION_ENTITIES:
                    return anchor
        if relation == "PART_OF":
            if any(token in f"{value} {raw_value}" for token in ("属于", "成员", "一部分", "组成", "系统", "卫星", "星系", "群", "带")):
                anchor = cls._extract_anchor_entity(value) or cls._extract_anchor_entity(raw_value)
                if anchor:
                    return anchor
        if relation in {"HAS_RADIUS", "HAS_MASS"}:
            quantity_source = raw_value or value
            if not cls._has_quantity_semantics(relation, quantity_source, ""):
                return ""
            if relation == "HAS_MASS":
                return cls._extract_canonical_mass(quantity_source)
            return cls._extract_canonical_radius(quantity_source)
        if relation == "HAS_ATMOSPHERE":
            return value
        if relation == "IS_A":
            return value
        return value

    @classmethod
    def _clean_graph_triple(cls, triple: dict) -> Optional[dict]:
        normalized = normalize_triple_record(triple)
        subject = cls._safe_name(normalized.get("subject", ""))
        relation = normalize_to_simplified(str(normalized.get("relation", "")).strip())
        raw = normalize_to_simplified(str(normalized.get("raw", "")).strip())
        pattern = normalize_to_simplified(str(normalized.get("pattern", "")).strip())
        if relation in {"HAS_RADIUS", "HAS_MASS"} and not cls._has_quantity_semantics(relation, raw, pattern):
            return None
        obj = cls._normalize_relation_object(relation, normalized.get("object", ""), raw=raw, subject=subject)
        if not subject or not relation or not obj:
            return None
        if relation not in cls.GRAPH_RELATION_WHITELIST:
            return None
        if not cls._is_valid_subject(subject):
            return None

        if relation == "DISCOVERED_BY":
            if not cls._is_valid_discoverer(obj):
                return None
        elif relation == "ORBITS":
            if not cls._is_valid_orbit_target(obj):
                return None
        elif relation == "IS_A":
            if not cls._is_valid_type_object(obj):
                return None
        elif relation == "LOCATED_IN":
            if not cls._is_valid_location_object(obj):
                return None
        elif relation == "PART_OF":
            if not cls._is_valid_part_of_object(obj):
                return None
        elif relation == "HAS_ATMOSPHERE":
            if not cls._is_valid_atmosphere_object(obj):
                return None
        elif relation in {"HAS_RADIUS", "HAS_MASS"}:
            if not cls._is_valid_quantity_object(obj, relation):
                return None
        else:
            return None

        return {
            "subject": subject,
            "relation": relation,
            "object": obj,
            "source": normalize_to_simplified(str(normalized.get("source", "")).strip()) or ACTIVE_SOURCE,
            "source_name": normalize_to_simplified(str(normalized.get("source_name", "")).strip())
            or normalize_to_simplified(str(normalized.get("source", "")).strip())
            or ACTIVE_SOURCE,
            "source_title": cls._safe_name(normalized.get("source_title", "")) or subject,
            "source_role": normalize_to_simplified(str(normalized.get("source_role", "")).strip()) or SOURCE_ROLE,
            "origin": normalize_to_simplified(str(normalized.get("origin", "")).strip()),
            "type": normalize_to_simplified(str(normalized.get("type", "")).strip()) or RECORD_TYPE_TRIPLE_CANDIDATE,
            "schema_version": normalize_to_simplified(str(normalized.get("schema_version", "")).strip())
            or get_source_schema_version(normalized.get("source_name") or normalized.get("source")),
            "pattern": pattern,
            "raw": raw,
        }

    @classmethod
    def _score_quantity_candidate(cls, triple: dict) -> int:
        relation = triple.get("relation", "")
        raw = normalize_to_simplified(str(triple.get("raw", "")))
        pattern = normalize_to_simplified(str(triple.get("pattern", "")))
        obj = normalize_to_simplified(str(triple.get("object", "")))
        score = 0

        if relation == "HAS_RADIUS":
            semantic_class = cls._radius_semantic_class(raw, pattern)
            class_scores = {
                "mean": 120,
                "generic": 100,
                "equatorial": 80,
                "polar": 75,
            }
            score += class_scores.get(semantic_class, 0)
            if "km" in obj:
                score += 30
            elif any(unit in obj for unit in ("光年", "kpc", "AU", "天文单位")):
                score += 10
        elif relation == "HAS_MASS":
            if any(token in raw for token in ("质量:", "質量:", "质量为", "質量為")):
                score += 120
            elif "mass" in raw.lower():
                score += 100
            if "kg" in obj:
                score += 30
            elif any(unit in obj for unit in ("太阳质量", "地球质量", "月球质量")):
                score += 10

        if pattern == "infobox":
            score += 30
        elif pattern == "rule":
            score += 5

        numeric = cls._parse_canonical_quantity_value(obj, relation)
        if numeric is None or numeric <= 0:
            return -1
        if relation == "HAS_RADIUS" and numeric > 0:
            score += 5
        if relation == "HAS_MASS" and numeric > 0:
            score += 5

        return score

    @staticmethod
    def _score_non_quantity_candidate(triple: dict) -> int:
        pattern = normalize_to_simplified(str(triple.get("pattern", "")))
        raw = normalize_to_simplified(str(triple.get("raw", "")))
        score = {
            "infobox": 40,
            "rule": 25,
            "supplemental_narrative": 10,
        }.get(pattern, 0)
        if raw:
            score += min(len(raw) // 40, 5)
        return score

    @classmethod
    def _score_graph_record(cls, record: Dict[str, str], query_context: dict) -> int:
        subject = normalize_to_simplified(str(record.get("subject", "")))
        relation = normalize_to_simplified(str(record.get("relation", "")))
        obj = normalize_to_simplified(str(record.get("object", "")))
        source_title = normalize_to_simplified(str(record.get("source_title", "") or record.get("source", "")))
        raw = normalize_to_simplified(str(record.get("raw", "")))
        primary = normalize_to_simplified(query_context.get("primary_entity", ""))
        entities = [normalize_to_simplified(str(item)).strip() for item in query_context.get("entities", []) if str(item).strip()]
        topic_terms = query_context.get("topic_terms", [])
        relation_hints = query_context.get("relation_hints", [])

        if relation not in cls.GRAPH_RELATION_WHITELIST:
            return -1
        if not cls._is_valid_subject(subject):
            return -1
        validators = {
            "DISCOVERED_BY": cls._is_valid_discoverer,
            "ORBITS": cls._is_valid_orbit_target,
            "IS_A": cls._is_valid_type_object,
            "LOCATED_IN": cls._is_valid_location_object,
            "PART_OF": cls._is_valid_part_of_object,
            "HAS_ATMOSPHERE": cls._is_valid_atmosphere_object,
        }
        if relation in {"HAS_RADIUS", "HAS_MASS"}:
            if not cls._is_valid_quantity_object(obj, relation):
                return -1
        elif relation in validators and not validators[relation](obj):
            return -1

        if cls._is_strict_relation_query(query_context):
            primary_relation = query_context["relation_hints"][0]
            if subject != primary or relation != primary_relation:
                return -1

        score = 0
        if entities:
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

    def load_all_triples(self, triples_dir=None):
        """加载所有三元组JSON文件到Neo4j"""
        if not self.driver:
            print("[Neo4j] 未连接，跳过导入")
            return 0, 0

        triples_dir = triples_dir or self.triples_dir or TRIPLES_DIR
        triple_files = glob.glob(os.path.join(triples_dir, '*_triples.json'))
        print(f"[Neo4j] 发现 {len(triple_files)} 个三元组文件")

        total_nodes = 0
        total_rels = 0
        created_nodes = {}  # name → label 缓存已创建的节点
        best_relation_triples = {}
        best_quantity_triples = {}

        for filepath in triple_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    triples = json.load(f)
            except:
                continue

            if not triples:
                continue

            fname = os.path.basename(filepath)
            print(f"[Neo4j] 处理: {fname} ({len(triples)} 个三元组)")
            page_title = self._safe_name(fname[:-len("_triples.json")])
            narrative_records = self._load_narrative_records(filepath)

            for triple in triples:
                cleaned = self._clean_graph_triple(triple)
                if not cleaned:
                    continue
                if cleaned["relation"] in {"HAS_RADIUS", "HAS_MASS"}:
                    key = (cleaned["subject"], cleaned["relation"])
                    existing = best_quantity_triples.get(key)
                    if existing is None or self._score_quantity_candidate(cleaned) > self._score_quantity_candidate(existing):
                        best_quantity_triples[key] = cleaned
                    continue
                key = (cleaned["subject"], cleaned["relation"], cleaned["object"])
                existing = best_relation_triples.get(key)
                if existing is None or self._score_non_quantity_candidate(cleaned) > self._score_non_quantity_candidate(existing):
                    best_relation_triples[key] = cleaned

            for derived in self._derive_supplemental_graph_triples(page_title, narrative_records):
                cleaned = self._clean_graph_triple(derived)
                if not cleaned:
                    continue
                key = (cleaned["subject"], cleaned["relation"], cleaned["object"])
                existing = best_relation_triples.get(key)
                if existing is None or self._score_non_quantity_candidate(cleaned) > self._score_non_quantity_candidate(existing):
                    best_relation_triples[key] = cleaned

        triples_to_import = list(best_relation_triples.values())
        triples_to_import.extend(best_quantity_triples.values())

        with self.driver.session() as session:
            for cleaned in triples_to_import:
                subj = cleaned["subject"]
                obj = cleaned["object"]
                rel = cleaned["relation"]
                source_name = cleaned["source"]
                source_title = cleaned["source_title"]
                source_role = cleaned.get("source_role", SOURCE_ROLE)
                schema_version = cleaned.get("schema_version", "") or get_source_schema_version(source_name)
                origin = cleaned["origin"]
                record_type = cleaned["type"]
                pattern = cleaned["pattern"]
                raw = cleaned["raw"]

                subj_label = self._infer_label(subj, rel)
                obj_label = self._infer_label(obj, '')

                if subj not in created_nodes:
                    try:
                        session.run(
                            f"MERGE (n:{subj_label} {{name: $name}}) "
                            f"ON CREATE SET n.source_title = $source_title, n.source = $source_name, n.source_role = $source_role, n.origin = $origin, n.schema_version = $schema_version "
                            f"ON MATCH SET n.source_title = coalesce(n.source_title, $source_title), "
                            f"n.source = coalesce(n.source, $source_name), "
                            f"n.source_role = coalesce(n.source_role, $source_role), "
                            f"n.origin = coalesce(n.origin, $origin), "
                            f"n.schema_version = coalesce(n.schema_version, $schema_version)",
                            name=subj,
                            source_title=source_title,
                            source_name=source_name,
                            source_role=source_role,
                            origin=origin,
                            schema_version=schema_version,
                        )
                        created_nodes[subj] = subj_label
                        total_nodes += 1
                    except Exception as e:
                        print(f"  创建节点失败 '{subj}': {e}")
                        continue

                if obj not in created_nodes:
                    try:
                        session.run(
                            f"MERGE (n:{obj_label} {{name: $name}}) "
                            f"ON CREATE SET n.source_title = $source_title, n.source = $source_name, n.source_role = $source_role, n.origin = $origin, n.schema_version = $schema_version "
                            f"ON MATCH SET n.source_title = coalesce(n.source_title, $source_title), "
                            f"n.source = coalesce(n.source, $source_name), "
                            f"n.source_role = coalesce(n.source_role, $source_role), "
                            f"n.origin = coalesce(n.origin, $origin), "
                            f"n.schema_version = coalesce(n.schema_version, $schema_version)",
                            name=obj,
                            source_title=source_title,
                            source_name=source_name,
                            source_role=source_role,
                            origin=origin,
                            schema_version=schema_version,
                        )
                        created_nodes[obj] = obj_label
                        total_nodes += 1
                    except Exception:
                        continue

                try:
                    session.run(
                        f"MATCH (a:{subj_label} {{name: $subj_name}}) "
                        f"MATCH (b:{obj_label} {{name: $obj_name}}) "
                        f"MERGE (a)-[r:{rel} {{source_title: $source_title, pattern: $pattern}}]->(b) "
                        f"SET r.source = $source_name, r.raw = $raw, r.origin = $origin, r.type = $record_type, "
                        f"r.source_role = $source_role, r.schema_version = $schema_version",
                        subj_name=subj,
                        obj_name=obj,
                        source_name=source_name,
                        source_title=source_title,
                        pattern=pattern,
                        raw=raw,
                        origin=origin,
                        record_type=record_type,
                        source_role=source_role,
                        schema_version=schema_version,
                    )
                    total_rels += 1
                except Exception as e:
                    print(f"  创建关系失败 '{subj}' -[{rel}]-> '{obj}': {e}")

        print(f"\n[Neo4j] 导入完成！节点: {total_nodes}, 关系: {total_rels}")
        return total_nodes, total_rels

    def search_graph(self, query_context: dict, limit: int = 20, source_filter: Optional[List[str]] = None) -> List[dict]:
        """按抽取出的实体和关系意图检索图谱，再做质量过滤。"""
        if not self.driver:
            return self._search_local_graph_mirror(query_context, limit=limit, source_filter=source_filter)

        entities = [item for item in query_context.get("entities", []) if item]
        if not entities and query_context.get("primary_entity"):
            entities = [query_context["primary_entity"]]
        if not entities:
            return []

        relation_hints = [item for item in query_context.get("relation_hints", []) if item]
        candidate_limit = max(limit * 8, 40)
        primary = self._safe_name(query_context.get("primary_entity", ""))
        source_filter = normalize_source_filter(source_filter, fallback_source=self.source_name)
        if self._is_strict_relation_query(query_context):
            cypher = (
                "MATCH (n)-[r]->(m) "
                "WHERE n.name = $primary "
                "AND type(r) IN $relations "
                "RETURN n.name AS subject, type(r) AS relation, m.name AS object, "
                "coalesce(r.source_title, '') AS source_title, "
                "coalesce(r.source, $default_source) AS source_name, "
                "coalesce(r.source_role, $default_source_role) AS source_role, "
                "coalesce(r.origin, '') AS origin, "
                "coalesce(r.schema_version, $default_schema_version) AS schema_version, "
                "coalesce(r.raw, '') AS raw "
                "LIMIT $candidate_limit"
            )
            params = {
                "primary": primary,
                "relations": relation_hints,
                "candidate_limit": candidate_limit,
                "default_source": self.source_name,
                "default_source_role": SOURCE_ROLE,
                "default_schema_version": get_source_schema_version(self.source_name),
            }
        else:
            cypher = (
                "MATCH (n)-[r]->(m) "
                "WHERE any(entity IN $entities WHERE n.name = entity OR m.name = entity) "
                "AND ($relations = [] OR type(r) IN $relations) "
                "RETURN n.name AS subject, type(r) AS relation, m.name AS object, "
                "coalesce(r.source_title, '') AS source_title, "
                "coalesce(r.source, $default_source) AS source_name, "
                "coalesce(r.source_role, $default_source_role) AS source_role, "
                "coalesce(r.origin, '') AS origin, "
                "coalesce(r.schema_version, $default_schema_version) AS schema_version, "
                "coalesce(r.raw, '') AS raw "
                "LIMIT $candidate_limit"
            )
            params = {
                "entities": entities,
                "relations": relation_hints,
                "candidate_limit": candidate_limit,
                "default_source": self.source_name,
                "default_source_role": SOURCE_ROLE,
                "default_schema_version": get_source_schema_version(self.source_name),
            }

        try:
            with self.driver.session() as session:
                rows = [dict(record) for record in session.run(cypher, **params)]
        except Exception:
            return self._search_local_graph_mirror(query_context, limit=limit, source_filter=source_filter)

        ranked = []
        for row in rows:
            resolved_source = row.get("source_name") or self.source_name
            if resolved_source not in source_filter:
                continue
            score = self._score_graph_record(row, query_context)
            if score < 70:
                continue
            ranked.append({
                "subject": row["subject"],
                "relation": row["relation"],
                "object": row["object"],
                "source": resolved_source,
                "source_name": resolved_source,
                "source_title": row.get("source_title", ""),
                "source_role": row.get("source_role", SOURCE_ROLE),
                "origin": row.get("origin", ""),
                "schema_version": get_source_schema_version(resolved_source),
                "_score": score,
            })

        ranked.sort(key=lambda item: item["_score"], reverse=True)
        deduped = []
        seen = set()
        for item in ranked:
            key = (item["subject"], item["relation"], item["object"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        for item in deduped:
            item.pop("_score", None)
        if deduped:
            return deduped[:limit]
        return self._search_local_graph_mirror(query_context, limit=limit, source_filter=source_filter)

    def _search_local_graph_mirror(self, query_context: dict, limit: int = 20, source_filter: Optional[List[str]] = None) -> List[dict]:
        source_filter = normalize_source_filter(source_filter, fallback_source=self.source_name)
        ranked = []
        for filepath in glob.glob(os.path.join(self._get_local_graph_triples_dir(), '*_triples.json')):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    triples = json.load(f)
            except Exception:
                continue

            page_title = self._safe_name(os.path.basename(filepath)[:-len("_triples.json")])
            candidates = []
            for triple in triples:
                cleaned = self._clean_graph_triple(triple)
                if cleaned:
                    candidates.append(cleaned)
            narrative_records = self._load_narrative_records(filepath)
            for derived in self._derive_supplemental_graph_triples(page_title, narrative_records):
                cleaned = self._clean_graph_triple(derived)
                if cleaned:
                    candidates.append(cleaned)

            for candidate in candidates:
                resolved_source = candidate.get("source") or candidate.get("source_name") or self.source_name
                if resolved_source not in source_filter:
                    continue
                score = self._score_graph_record(candidate, query_context)
                if score < 70:
                    continue
                ranked.append({
                    "subject": candidate["subject"],
                    "relation": candidate["relation"],
                    "object": candidate["object"],
                    "source": resolved_source,
                    "source_name": candidate.get("source_name") or resolved_source,
                    "source_title": candidate.get("source_title", ""),
                    "source_role": candidate.get("source_role", SOURCE_ROLE),
                    "origin": candidate.get("origin", ""),
                    "schema_version": get_source_schema_version(resolved_source),
                    "_score": score,
                })

        ranked.sort(key=lambda item: item["_score"], reverse=True)
        deduped = []
        seen = set()
        for item in ranked:
            key = (item["subject"], item["relation"], item["object"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        for item in deduped:
            item.pop("_score", None)
        return deduped[:limit]

    def _get_local_graph_triples_dir(self) -> str:
        return self.triples_dir or TRIPLES_DIR

    def repair_source_isolation_metadata(self):
        """删除旧污染关系并按当前 triples 原位刷新 graph metadata。"""
        if not self.driver:
            return {"deleted_relationships": 0, "reloaded_relationships": 0, "remaining_relationships": 0}

        allowed = sorted(self.GRAPH_RELATION_WHITELIST)
        params = {
            "allowed": allowed,
            "active_source": ACTIVE_SOURCE,
            "source_role": SOURCE_ROLE,
        }
        count_query = (
            "MATCH ()-[r]->() "
            "WHERE NOT type(r) IN $allowed "
            "OR coalesce(r.source, '') <> $active_source "
            "OR coalesce(r.source_role, '') <> $source_role "
            "OR coalesce(r.origin, '') = '' "
            "RETURN count(r) AS c"
        )
        delete_query = (
            "MATCH ()-[r]->() "
            "WHERE NOT type(r) IN $allowed "
            "OR coalesce(r.source, '') <> $active_source "
            "OR coalesce(r.source_role, '') <> $source_role "
            "OR coalesce(r.origin, '') = '' "
            "DELETE r"
        )

        with self.driver.session() as session:
            deleted = session.run(count_query, **params).single()["c"]
            if deleted:
                session.run(delete_query, **params)

        _, reloaded_relationships = self.load_all_triples()

        with self.driver.session() as session:
            remaining = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]

        return {
            "deleted_relationships": deleted,
            "reloaded_relationships": reloaded_relationships,
            "remaining_relationships": remaining,
        }

    def get_stats(self):
        """获取数据库统计信息"""
        if not self.driver:
            return {'nodes': 0, 'rels': 0, 'rel_types': [], 'labels': []}

        with self.driver.session() as session:
            nodes = session.run("MATCH (n) RETURN count(n) AS c").single()['c']
            rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()['c']
            labels = [r[0] for r in session.run("CALL db.labels()").values()]
            rel_types = [r[0] for r in session.run("CALL db.relationshipTypes()").values()]

        return {
            'nodes': nodes,
            'rels': rels,
            'labels': labels,
            'rel_types': rel_types,
        }

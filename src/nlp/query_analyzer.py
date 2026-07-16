"""
Query analysis helpers for retrieval-oriented astronomy questions.
"""
import json
import os
import re
from functools import lru_cache
from typing import Iterable, List, Optional

from config import TERMS_JSON_PATH
from src.nlp.text_normalizer import normalize_to_simplified

_FALLBACK_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "及", "以及", "或", "有", "被", "把",
    "从", "到", "对", "为", "以", "上", "下", "中", "内", "外", "之", "而", "且",
    "但", "也", "都", "还", "又", "就", "更", "很", "太", "最", "较", "一下", "请问",
    "一下子", "这个", "那个", "这些", "那些", "什么", "哪个", "哪些", "多少", "几",
    "吗", "呢", "呀", "啊", "哦", "吧", "它", "他", "她", "它们", "他们", "她们",
    "自己", "本身", "一下", "一下儿",
    "为什么", "为何", "怎么", "如何", "请问",
}

_PRONOUN_TOKENS = {"它", "他", "她", "它们", "他们", "她们", "自己", "本身"}
_MATCH_CONNECTORS = {"的", "和", "与", "及", "以及", "、", "，", ",", " "}
_TOPIC_KEYWORDS = (
    "大气层", "大气", "成分", "稀薄", "公转", "轨道", "发现者", "发现", "卫星",
    "气压", "系统", "位置", "半径", "质量", "大小", "直径", "密度", "参数", "数据",
)

_SOLAR_LUMINOSITY_TOPIC_HINTS = (
    "核融合", "核心", "能量来源", "能量", "氢", "氦", "发光", "辐射",
)

_BUILTIN_ENTITY_TITLES = {
    "太阳", "水星", "金星", "地球", "月球", "火星", "木星", "土星", "天王星", "海王星",
    "冥王星", "谷神星", "火卫一", "火卫二", "木卫一", "木卫二", "木卫三", "木卫四",
    "土卫一", "土卫二", "土卫三", "土卫四", "土卫五", "土卫六", "土卫七", "土卫八",
    "天卫一", "天卫二", "天卫三", "天卫四", "天卫五", "海卫一", "冥卫一",
    "地球系统", "火星系统", "木星系统", "土星系统", "天王星系统", "海王星系统", "冥王星系统",
    "伽利略卫星",
}


@lru_cache(maxsize=1)
def _load_terms_json() -> dict:
    if not os.path.exists(TERMS_JSON_PATH):
        return {}
    try:
        with open(TERMS_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _build_stopwords() -> set:
    terms = _load_terms_json()
    stopwords = set(_FALLBACK_STOPWORDS)
    skip_words = terms.get("skip_words", {})
    for items in skip_words.values():
        if isinstance(items, list):
            stopwords.update(normalize_to_simplified(str(item)).strip() for item in items if str(item).strip())
    stopwords.update(_PRONOUN_TOKENS)
    return {item for item in stopwords if item}


def _normalize_token(text: str) -> str:
    value = normalize_to_simplified(str(text or "")).strip()
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value)
    return value


def _compact_for_match(text: str) -> str:
    value = _normalize_token(text)
    for token in _MATCH_CONNECTORS:
        value = value.replace(token, "")
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", value)


@lru_cache(maxsize=1)
def _get_jieba():
    try:
        import jieba  # type: ignore
    except Exception:
        return None

    terms = _load_terms_json()
    for value in _iter_terms(terms):
        if value:
            try:
                jieba.add_word(value)
            except Exception:
                continue
    return jieba


def _iter_terms(node) -> Iterable[str]:
    if isinstance(node, dict):
        for value in node.values():
            yield from _iter_terms(value)
        return
    if isinstance(node, list):
        for value in node:
            yield from _iter_terms(value)
        return
    if isinstance(node, str):
        normalized = _normalize_token(node)
        if normalized:
            yield normalized


def _segment_query(query: str, extra_terms: Optional[Iterable[str]] = None) -> List[str]:
    normalized = _normalize_token(query)
    jieba = _get_jieba()
    if jieba is not None:
        for term in extra_terms or ():
            term = _normalize_token(term)
            if term:
                try:
                    jieba.add_word(term)
                except Exception:
                    continue
        raw_tokens = jieba.lcut(normalized, cut_all=False)
    else:
        raw_tokens = re.findall(r"[A-Za-z]+(?:\s+[A-Za-z0-9]+)*|[\u4e00-\u9fff]{1,}", normalized)

    tokens = []
    stopwords = _build_stopwords()
    for raw in raw_tokens:
        token = _normalize_token(raw)
        if not token:
            continue
        if token in stopwords:
            continue
        if len(token) == 1 and not re.search(r"[A-Za-z0-9]", token):
            continue
        tokens.append(token)
    return tokens


def _append_unique(items: List[str], value: str):
    value = _normalize_token(value)
    if value and value not in items:
        items.append(value)


def build_query_context(
    query: str,
    known_titles: Optional[Iterable[str]] = None,
    alias_map: Optional[dict] = None,
    max_topic_terms: int = 8,
) -> dict:
    normalized = _normalize_token(query)
    lowered = normalized.lower()
    titles = sorted(
        {
            _normalize_token(title)
            for title in list(known_titles or []) + list(_BUILTIN_ENTITY_TITLES)
            if _normalize_token(title)
        },
        key=len,
        reverse=True,
    )
    compact_query = _compact_for_match(normalized)
    aliases = alias_map or {}

    entities: List[str] = []
    for alias, canonical in aliases.items():
        if _normalize_token(alias).lower() in lowered:
            _append_unique(entities, canonical)

    for title in titles:
        compact_title = _compact_for_match(title)
        if title in normalized or (compact_title and compact_title in compact_query):
            _append_unique(entities, title)

    segments = _segment_query(normalized, extra_terms=titles)

    compact_title_map = {
        _compact_for_match(title): title
        for title in titles
        if _compact_for_match(title)
    }
    for token in segments:
        mapped = aliases.get(token.lower()) or aliases.get(token)
        if mapped:
            _append_unique(entities, mapped)
            continue
        matched = compact_title_map.get(_compact_for_match(token))
        if matched:
            _append_unique(entities, matched)

    primary_entity = entities[0] if entities else ""
    topic_terms: List[str] = []
    for token in _TOPIC_KEYWORDS:
        if token in normalized:
            _append_unique(topic_terms, token)

    topic_intents: List[str] = []
    solar_luminosity_query = (
        ("太阳" in normalized or any(entity == "太阳" for entity in entities))
        and any(token in normalized for token in ("发光", "会亮", "亮光", "能量来源", "释放能量"))
    )
    if solar_luminosity_query:
        topic_intents.append("solar_luminosity")
        for token in _SOLAR_LUMINOSITY_TOPIC_HINTS:
            _append_unique(topic_terms, token)
    if any(token in normalized for token in ("不存在", "虚构", "并不存在")):
        topic_intents.append("negative_absence")

    entity_compacts = {_compact_for_match(entity) for entity in entities if entity}
    for token in segments:
        compact_token = _compact_for_match(token)
        if compact_token in entity_compacts:
            continue
        if token in _PRONOUN_TOKENS:
            continue
        _append_unique(topic_terms, token)

    relation_hints = []
    if any(token in normalized for token in ("绕谁", "绕", "公转", "环绕", "轨道", "的卫星", "的行星", "所属行星", "所属的行星")):
        relation_hints.append("ORBITS")
    if any(token in normalized for token in ("谁发现", "发现者", "发现了", "发现的", "由")) and "发现" in normalized:
        relation_hints.append("DISCOVERED_BY")
    if any(token in normalized for token in ("大气", "大气层", "气压")):
        relation_hints.append("HAS_ATMOSPHERE")
    explicit_location = any(token in normalized for token in ("在哪里", "位于哪里", "在哪", "位于", "位在"))
    location_pattern = (
        (re.search(r"在.+中", normalized) or re.search(r"位于.+内", normalized))
        and "数据集中" not in normalized
    )
    if explicit_location or location_pattern:
        relation_hints.append("LOCATED_IN")
    if "属于什么系统" in normalized:
        relation_hints.append("PART_OF")
    elif "属于什么" in normalized or "属于哪里" in normalized or "属于哪" in normalized or "属于哪类" in normalized or "是一部分" in normalized:
        relation_hints.append("PART_OF")
    if "半径" in normalized:
        relation_hints.append("HAS_RADIUS")
    if "直径" in normalized:
        relation_hints.append("HAS_RADIUS")
        topic_intents.append("diameter")
    if "质量" in normalized:
        relation_hints.append("HAS_MASS")
    if "有多大" in normalized or "多大" in normalized:
        relation_hints.extend(["HAS_RADIUS", "HAS_MASS"])
    if any(token in normalized for token in ("是什么类型", "什么类型", "特殊类型", "被标注为", "标注为", "类型")):
        relation_hints.append("IS_A")

    return {
        "query": normalized,
        "entities": entities,
        "primary_entity": primary_entity,
        "topic_terms": topic_terms[:max_topic_terms],
        "topic_intents": topic_intents,
        "relation_hints": list(dict.fromkeys(relation_hints)),
        "segments": segments,
    }

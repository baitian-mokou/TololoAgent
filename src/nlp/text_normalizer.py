"""
中文文本归一化：统一将简繁混合内容转换为简体
"""
from __future__ import annotations

from src.source_control import (
    ACTIVE_SOURCE,
    RECORD_TYPE_EMBEDDING_CHUNK,
    RECORD_TYPE_TRIPLE_CANDIDATE,
    SOURCE_ROLE,
    is_known_source,
    normalize_origin,
    get_source_schema_version,
)

try:
    from opencc import OpenCC
except ImportError:
    OpenCC = None


_OPENCC = OpenCC("t2s") if OpenCC is not None else None


def normalize_to_simplified(text):
    """将文本统一转换为简体；依赖缺失时退回原文"""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text or _OPENCC is None:
        return text
    return _OPENCC.convert(text)


def normalize_triple_record(triple: dict) -> dict:
    """统一三元组中的文本字段"""
    normalized = dict(triple or {})
    for key in ("subject", "object", "raw", "source", "source_title", "origin", "type", "source_role"):
        if key in normalized and normalized[key] is not None:
            normalized[key] = normalize_to_simplified(normalized[key]).strip()

    legacy_source = normalized.get("source", "")
    if legacy_source and not is_known_source(legacy_source) and not normalized.get("source_title"):
        normalized["source_title"] = legacy_source
        normalized["source"] = ACTIVE_SOURCE

    resolved_source = normalized.get("source") or normalized.get("source_name") or ACTIVE_SOURCE
    if not normalized.get("source"):
        normalized["source"] = resolved_source
    if not normalized.get("source_name"):
        normalized["source_name"] = normalized.get("source") or resolved_source
    if not normalized.get("source_title"):
        normalized["source_title"] = normalized.get("subject", "")
    if not normalized.get("source_role"):
        normalized["source_role"] = SOURCE_ROLE
    normalized["origin"] = normalize_origin(normalized.get("origin"))
    if not normalized.get("type"):
        normalized["type"] = RECORD_TYPE_TRIPLE_CANDIDATE
    if not normalized.get("schema_version"):
        normalized["schema_version"] = get_source_schema_version(normalized.get("source") or resolved_source)
    return normalized


def normalize_narrative_record(narrative: dict) -> dict:
    """统一叙事块中的文本字段"""
    normalized = dict(narrative or {})
    for key in ("page_title", "section", "content", "source", "source_title", "origin", "type", "path", "source_role"):
        if key in normalized and normalized[key] is not None:
            normalized[key] = normalize_to_simplified(normalized[key]).strip()

    keywords = normalized.get("keywords")
    if isinstance(keywords, list):
        normalized["keywords"] = [
            normalize_to_simplified(keyword).strip()
            for keyword in keywords
            if keyword
        ]
    elif isinstance(keywords, str):
        normalized["keywords"] = normalize_to_simplified(keywords).strip()

    legacy_source = normalized.get("source", "")
    if legacy_source and not is_known_source(legacy_source) and not normalized.get("source_title"):
        normalized["source_title"] = legacy_source
        normalized["source"] = ACTIVE_SOURCE

    resolved_source = normalized.get("source") or normalized.get("source_name") or ACTIVE_SOURCE
    if not normalized.get("source"):
        normalized["source"] = resolved_source
    if not normalized.get("source_name"):
        normalized["source_name"] = normalized.get("source") or resolved_source
    if not normalized.get("source_title"):
        normalized["source_title"] = normalized.get("page_title", "")
    if not normalized.get("source_role"):
        normalized["source_role"] = SOURCE_ROLE
    normalized["origin"] = normalize_origin(normalized.get("origin"))
    if not normalized.get("type"):
        normalized["type"] = RECORD_TYPE_EMBEDDING_CHUNK
    if not normalized.get("schema_version"):
        normalized["schema_version"] = get_source_schema_version(normalized.get("source") or resolved_source)
    return normalized

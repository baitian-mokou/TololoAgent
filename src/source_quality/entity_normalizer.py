from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


ENTITY_ALIASES: Dict[str, Dict[str, object]] = {
    "Q525": {"label": "太阳", "aliases": ["太阳", "Sun", "the Sun"]},
    "Q2": {"label": "地球", "aliases": ["地球", "Earth"]},
    "Q405": {"label": "月球", "aliases": ["月球", "Moon", "the Moon"]},
    "Q111": {"label": "火星", "aliases": ["火星", "Mars"]},
    "Q313": {"label": "金星", "aliases": ["金星", "Venus"]},
    "Q319": {"label": "木星", "aliases": ["木星", "Jupiter"]},
    "Q193": {"label": "土星", "aliases": ["土星", "Saturn"]},
    "Q324": {"label": "天王星", "aliases": ["天王星", "Uranus"]},
    "Q332": {"label": "海王星", "aliases": ["海王星", "Neptune"]},
    "Q339": {"label": "冥王星", "aliases": ["冥王星", "Pluto"]},
    "Q596": {"label": "谷神星", "aliases": ["谷神星", "Ceres"]},
    "Q7547": {"label": "火卫一", "aliases": ["火卫一", "Phobos"]},
    "Q3143": {"label": "木卫二", "aliases": ["木卫二", "Europa"]},
    "Q3134": {"label": "木卫四", "aliases": ["木卫四", "Callisto"]},
}

_ALIAS_INDEX: Dict[str, str] = {}
for qid, payload in ENTITY_ALIASES.items():
    _ALIAS_INDEX[qid.lower()] = qid
    for alias in payload["aliases"]:
        normalized = re.sub(r"\s+", " ", str(alias).strip()).lower()
        _ALIAS_INDEX[normalized] = qid


def normalize_entity(value: Any) -> Dict[str, object]:
    raw = str(value or "").strip()
    normalized = re.sub(r"\s+", " ", raw).lower()
    qid = _ALIAS_INDEX.get(normalized)
    if not qid and raw.upper().startswith("Q") and raw[1:].isdigit():
        qid = raw.upper()
    if qid and qid in ENTITY_ALIASES:
        payload = ENTITY_ALIASES[qid]
        return {
            "raw_value": raw,
            "canonical_id": qid,
            "canonical_label": payload["label"],
            "aliases": list(payload["aliases"]),
            "parse_status": "entity_normalized",
        }
    if qid:
        return {
            "raw_value": raw,
            "canonical_id": qid,
            "canonical_label": qid,
            "aliases": [qid],
            "parse_status": "qid_unknown_alias",
        }
    return {
        "raw_value": raw,
        "canonical_id": "",
        "canonical_label": raw,
        "aliases": [raw] if raw else [],
        "parse_status": "unmapped_entity",
    }


def entity_groups_equivalent(values_by_source: Dict[str, Iterable[str]]) -> bool:
    groups: List[set[str]] = []
    for values in values_by_source.values():
        ids = {str(normalize_entity(value).get("canonical_id") or "") for value in values}
        ids = {item for item in ids if item}
        if not ids:
            return False
        groups.append(ids)
    baseline = groups[0]
    return all(bool(baseline.intersection(group)) for group in groups[1:])

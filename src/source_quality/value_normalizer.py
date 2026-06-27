from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.source_quality.unit_registry import lookup_unit_qid


EARTH_MASS_KG = 5.97237e24
JUPITER_MASS_KG = 1.8982e27
CANONICAL_ATMOSPHERE_ORDER = ("CO2", "N2", "Ar", "O2", "H2O", "CO", "CH4", "He", "H2")

ATMOSPHERE_ALIASES = {
    "co2": "CO2",
    "co₂": "CO2",
    "二氧化碳": "CO2",
    "carbon dioxide": "CO2",
    "n2": "N2",
    "n₂": "N2",
    "氮气": "N2",
    "nitrogen": "N2",
    "ar": "Ar",
    "氩气": "Ar",
    "argon": "Ar",
    "o2": "O2",
    "o₂": "O2",
    "氧气": "O2",
    "oxygen": "O2",
    "h2o": "H2O",
    "h₂o": "H2O",
    "水蒸气": "H2O",
    "水气": "H2O",
    "water vapor": "H2O",
    "water vapour": "H2O",
    "co": "CO",
    "一氧化碳": "CO",
    "carbon monoxide": "CO",
    "ch4": "CH4",
    "ch₄": "CH4",
    "甲烷": "CH4",
    "methane": "CH4",
    "he": "He",
    "氦": "He",
    "氦气": "He",
    "helium": "He",
    "h2": "H2",
    "h₂": "H2",
    "氢": "H2",
    "氢气": "H2",
    "hydrogen": "H2",
}


def normalize_value(raw_value: Any, relation: str = "") -> Dict[str, Any]:
    relation_name = str(relation or "").strip()
    if relation_name == "HAS_MASS":
        return normalize_mass(raw_value, relation_name)
    if relation_name == "HAS_RADIUS":
        return normalize_radius(raw_value, relation_name)
    if relation_name == "HAS_ATMOSPHERE":
        return normalize_atmosphere(raw_value, relation_name)
    return normalize_text_value(raw_value, relation_name)


def normalize_mass(raw_value: Any, relation: str) -> Dict[str, Any]:
    text = normalize_scientific_text(raw_value)
    qid_result = normalize_quantity_unit_qid(raw_value, relation, expected_dimensions={"mass"})
    if qid_result:
        return qid_result
    number = parse_first_number(text)
    multiplier = 1.0
    unit = ""
    if number is not None:
        if re.search(r"(地球质量|earth mass(?:es)?|m⊕|m_earth)", text, flags=re.IGNORECASE):
            multiplier = EARTH_MASS_KG
            unit = "kg"
        elif re.search(r"(木星质量|jupiter mass(?:es)?|m[j♃]|m_jupiter)", text, flags=re.IGNORECASE):
            multiplier = JUPITER_MASS_KG
            unit = "kg"
        elif re.search(r"(千克|公斤|kg)", text, flags=re.IGNORECASE):
            unit = "kg"
        if unit == "kg":
            value = number * multiplier
            return result(raw_value, format_number(value), "kg", value, relation, 0.95, "parsed")
    return result(raw_value, canonical_text(raw_value), "", None, relation, 0.2, "unparsed")


def normalize_radius(raw_value: Any, relation: str) -> Dict[str, Any]:
    text = normalize_scientific_text(raw_value)
    qid_result = normalize_quantity_unit_qid(raw_value, relation, expected_dimensions={"length", "distance"})
    if qid_result:
        return qid_result
    number = parse_first_number(text)
    if number is not None:
        if re.search(r"\b(m|meter|metre|meters|metres)\b|米", text, flags=re.IGNORECASE) and not re.search(r"\bkm\b|千米|公里", text, flags=re.IGNORECASE):
            value = number / 1000.0
            return result(raw_value, format_number(value), "km", value, relation, 0.95, "parsed")
        if re.search(r"\b(km|kilometer|kilometre|kilometers|kilometres)\b|千米|公里", text, flags=re.IGNORECASE):
            return result(raw_value, format_number(number), "km", number, relation, 0.95, "parsed")
    return result(raw_value, canonical_text(raw_value), "", None, relation, 0.2, "unparsed")


def normalize_atmosphere(raw_value: Any, relation: str) -> Dict[str, Any]:
    text = canonical_text(raw_value)
    found = []
    for alias, canonical in ATMOSPHERE_ALIASES.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text, flags=re.IGNORECASE) or alias in text:
            found.append(canonical)
    unique = ordered_unique(found, CANONICAL_ATMOSPHERE_ORDER)
    if unique:
        parse_status = "synonym_normalized" if any(item not in text for item in unique) else "parsed"
        return result(raw_value, ";".join(unique), "component_set", None, relation, 0.9, parse_status)
    return result(raw_value, canonical_text(raw_value), "", None, relation, 0.2, "unparsed")


def normalize_text_value(raw_value: Any, relation: str) -> Dict[str, Any]:
    normalized = canonical_text(raw_value)
    return result(raw_value, normalized, "", None, relation, 0.5 if normalized else 0.0, "text_normalized" if normalized else "empty")


def normalize_quantity_unit_qid(raw_value: Any, relation: str, *, expected_dimensions: set[str]) -> Dict[str, Any]:
    text = normalize_scientific_text(raw_value)
    match = re.search(r"([+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?)\s+(Q\d+)", text, flags=re.IGNORECASE)
    if not match:
        return {}
    number = float(match.group(1))
    unit_qid = match.group(2).upper()
    unit_record = lookup_unit_qid(unit_qid)
    if not unit_record:
        payload = result(raw_value, canonical_text(raw_value), "", None, relation, 0.0, "unknown_unit")
        payload["unit_qid"] = unit_qid
        return payload
    dimension = str(unit_record.get("dimension", "unknown"))
    if dimension not in expected_dimensions:
        payload = result(raw_value, canonical_text(raw_value), "", None, relation, 0.1, "unit_dimension_mismatch")
        payload["unit_qid"] = unit_qid
        payload["unit_record"] = unit_record
        return payload
    numeric_value = number * float(unit_record.get("conversion_factor", 1.0))
    payload = result(
        raw_value,
        format_number(numeric_value),
        str(unit_record.get("canonical_unit", "")),
        numeric_value,
        relation,
        0.95,
        "parsed",
    )
    payload["unit_qid"] = unit_qid
    payload["unit_record"] = unit_record
    return payload


def result(
    raw_value: Any,
    normalized_value: str,
    normalized_unit: str,
    numeric_value: Optional[float],
    relation: str,
    confidence: float,
    parse_status: str,
) -> Dict[str, Any]:
    return {
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "normalized_unit": normalized_unit,
        "numeric_value": numeric_value,
        "relation": relation,
        "confidence": confidence,
        "parse_status": parse_status,
    }


def values_equivalent(left: Dict[str, Any], right: Dict[str, Any], *, rel_tol: float = 0.002) -> bool:
    if left.get("normalized_unit") and left.get("normalized_unit") == right.get("normalized_unit"):
        left_number = left.get("numeric_value")
        right_number = right.get("numeric_value")
        if left_number is not None and right_number is not None:
            return math.isclose(float(left_number), float(right_number), rel_tol=rel_tol, abs_tol=1e-9)
    return bool(left.get("normalized_value")) and left.get("normalized_value") == right.get("normalized_value")


def normalize_scientific_text(raw_value: Any) -> str:
    text = canonical_text(raw_value)
    text = text.replace(",", "")
    text = re.sub(r"(\d+\.\d+)\s+(\d+)", r"\1\2", text)
    text = re.sub(r"×\s*10\s*\^\s*([+-]?\d+)", r"e\1", text)
    text = re.sub(r"×\s*10\s*([+-]?\d+)", r"e\1", text)
    text = re.sub(r"x\s*10\s*\^\s*([+-]?\d+)", r"e\1", text, flags=re.IGNORECASE)
    text = re.sub(r"x\s*10\s*([+-]?\d+)", r"e\1", text, flags=re.IGNORECASE)
    text = re.sub(r"10\^([+-]?\d+)", r"1e\1", text)
    text = re.sub(r"(\d)\s+e", r"\1e", text)
    return text


def parse_first_number(text: str) -> Optional[float]:
    match = re.search(r"([+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?)", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def canonical_text(raw_value: Any) -> str:
    text = str(raw_value or "").strip()
    text = text.replace("；", ";").replace("，", ",")
    text = re.sub(r"\s+", " ", text)
    return text


def format_number(value: float) -> str:
    return f"{value:.12g}"


def ordered_unique(values: Iterable[str], preferred_order: Iterable[str]) -> List[str]:
    seen = set()
    output = []
    for item in preferred_order:
        if item in values and item not in seen:
            seen.add(item)
            output.append(item)
    for item in values:
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output

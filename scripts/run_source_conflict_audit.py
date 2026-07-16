from __future__ import annotations

import glob
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import BASE_DIR, TRIPLES_DIR
from src.source_quality.entity_normalizer import entity_groups_equivalent
from src.source_quality.measurement_kind import infer_measurement_kind
from src.source_quality.value_normalizer import normalize_value, values_equivalent


SOURCES = ("zh_wikipedia", "wikidata", "nasa")
REQUIRED_METADATA_FIELDS = (
    "source",
    "source_name",
    "source_role",
    "origin",
    "schema_version",
    "source_title",
)
REPORT_JSON = os.path.join(BASE_DIR, "evaluation", "source_conflict_audit.json")
REPORT_MD = os.path.join(BASE_DIR, "docs", "source_conflict_audit.md")
REPORT_V2_JSON = os.path.join(BASE_DIR, "evaluation", "source_conflict_audit_v2.json")
REPORT_V2_MD = os.path.join(BASE_DIR, "docs", "source_conflict_audit_v2.md")
REPORT_V3_JSON = os.path.join(BASE_DIR, "evaluation", "source_conflict_audit_v3.json")
REPORT_V3_MD = os.path.join(BASE_DIR, "docs", "source_conflict_audit_v3.md")
REPORT_V4_JSON = os.path.join(BASE_DIR, "evaluation", "source_conflict_audit_v4.json")
REPORT_V4_MD = os.path.join(BASE_DIR, "docs", "source_conflict_audit_v4.md")
NASA_PREVIEW_REPORT = os.path.join(BASE_DIR, "evaluation", "source_expansion", "nasa", "nasa_live_preview_report.json")
QUALITY_PATCH_DIR = os.path.join(BASE_DIR, "data", "quality_patches")
QUALITY_PATCH_CANDIDATES = os.path.join(QUALITY_PATCH_DIR, "source_conflict_resolution_candidates.json")


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_source_triples(source: str) -> List[Dict[str, Any]]:
    if source == "zh_wikipedia":
        pattern = os.path.join(TRIPLES_DIR, "*_triples.json")
    else:
        pattern = os.path.join(TRIPLES_DIR, source, "*_triples.json")
    records: List[Dict[str, Any]] = []
    for path in sorted(glob.glob(pattern)):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            records.append({
                "_load_error": str(exc),
                "_path": path,
                "source": source,
                "source_name": source,
            })
            continue
        if isinstance(payload, list):
            for record in payload:
                if isinstance(record, dict):
                    item = dict(record)
                    item["_path"] = path
                    records.append(item)
    return records


def metadata_breaks(source: str, records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    breaks = []
    for index, record in enumerate(records):
        if record.get("_load_error"):
            breaks.append({
                "source": source,
                "path": record.get("_path", ""),
                "index": index,
                "missing_or_invalid": ["load_error"],
                "error": record.get("_load_error"),
            })
            continue
        missing = [field for field in REQUIRED_METADATA_FIELDS if not str(record.get(field, "")).strip()]
        if record.get("source") != source or record.get("source_name") != source:
            missing.append("source/source_name")
        if missing:
            breaks.append({
                "source": source,
                "path": record.get("_path", ""),
                "index": index,
                "subject": record.get("subject", ""),
                "relation": record.get("relation", ""),
                "missing_or_invalid": sorted(set(missing)),
            })
    return breaks


def normalize_object(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def parse_numeric_with_unit(value: Any) -> Tuple[float | None, str]:
    text = normalize_object(value)
    text = text.replace(",", "")
    text = re.sub(r"×\s*10\s*([+-]?\d+)", r"e\1", text)
    text = re.sub(r"x\s*10\s*([+-]?\d+)", r"e\1", text)
    text = re.sub(r"(\d)\s+e", r"\1e", text)
    match = re.search(r"([+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?)\s*([a-z]+)?", text)
    if not match:
        return None, ""
    try:
        number = float(match.group(1))
    except ValueError:
        return None, ""
    unit = canonical_unit(match.group(2) or "")
    return number, unit


def canonical_unit(unit: str) -> str:
    value = str(unit or "").strip().lower()
    aliases = {
        "kilometre": "km",
        "kilometer": "km",
        "kilometres": "km",
        "kilometers": "km",
        "kgs": "kg",
    }
    return aliases.get(value, value)


def objects_exact_match(values_by_source: Dict[str, List[str]]) -> bool:
    normalized_sets = {source: {normalize_object(value) for value in values} for source, values in values_by_source.items()}
    if not normalized_sets:
        return False
    first = next(iter(normalized_sets.values()))
    return all(values == first for values in normalized_sets.values())


def objects_unit_equivalent(values_by_source: Dict[str, List[str]]) -> bool:
    parsed = {}
    for source, values in values_by_source.items():
        numeric_values = []
        for value in values:
            number, unit = parse_numeric_with_unit(value)
            if number is not None and unit:
                numeric_values.append((number, unit))
        if not numeric_values:
            return False
        parsed[source] = numeric_values
    units = {unit for values in parsed.values() for _, unit in values}
    if len(units) != 1:
        return False
    representatives = [values[0][0] for values in parsed.values()]
    baseline = representatives[0]
    return all(math.isclose(baseline, other, rel_tol=0.002, abs_tol=1e-9) for other in representatives[1:])


def build_index(records_by_source: Dict[str, List[Dict[str, Any]]]) -> Dict[Tuple[str, str], Dict[str, List[Dict[str, Any]]]]:
    index: Dict[Tuple[str, str], Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for source, records in records_by_source.items():
        for record in records:
            subject = str(record.get("subject") or "").strip()
            relation = str(record.get("relation") or "").strip()
            if subject and relation and not record.get("_load_error"):
                index[(subject, relation)][source].append(record)
    return index


def classify_key(key: Tuple[str, str], records_by_source: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    present_sources = sorted(records_by_source.keys())
    missing_sources = [source for source in SOURCES if source not in records_by_source]
    values_by_source = {
        source: [str(record.get("object", "")) for record in records]
        for source, records in records_by_source.items()
    }
    statuses = []
    if missing_sources:
        statuses.append("source_missing")
    if len(present_sources) >= 2:
        if objects_exact_match(values_by_source):
            statuses.append("exact_match")
        elif objects_unit_equivalent(values_by_source):
            statuses.append("unit_equivalent")
        else:
            statuses.append("value_conflict")
    return {
        "subject": key[0],
        "relation": key[1],
        "status": statuses,
        "present_sources": present_sources,
        "missing_sources": missing_sources,
        "values_by_source": values_by_source,
    }


def normalize_values_by_source(relation: str, values_by_source: Dict[str, List[str]]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        source: [normalize_value(value, relation) for value in values]
        for source, values in values_by_source.items()
    }


def classify_key_v2(
    key: Tuple[str, str],
    records_by_source: Dict[str, List[Dict[str, Any]]],
    metadata_keys_with_breaks: set[Tuple[str, str]],
) -> Dict[str, Any]:
    subject, relation = key
    present_sources = sorted(records_by_source.keys())
    missing_sources = [source for source in SOURCES if source not in records_by_source]
    values_by_source = {
        source: [str(record.get("object", "")) for record in records]
        for source, records in records_by_source.items()
    }
    normalized_by_source = normalize_values_by_source(relation, values_by_source)
    statuses: List[str] = []
    reasons: List[str] = []
    if missing_sources:
        statuses.append("source_missing")
        reasons.append(f"Missing sources: {', '.join(missing_sources)}.")
    if key in metadata_keys_with_breaks:
        statuses.append("insufficient_metadata")
        reasons.append("One or more records for this key have incomplete metadata.")
    if len(present_sources) >= 2:
        if objects_exact_match(values_by_source):
            statuses.append("exact_match")
            reasons.append("Raw object strings match after whitespace/case normalization.")
        elif group_numeric_equivalent(normalized_by_source):
            statuses.append("unit_equivalent")
            reasons.append("Numeric values normalize to the same base unit within tolerance.")
        elif group_normalized_equivalent(normalized_by_source):
            statuses.append("normalized_equivalent")
            reasons.append("Normalized values match even though raw strings differ.")
        elif relation == "HAS_ATMOSPHERE" and group_atmosphere_synonym_equivalent(normalized_by_source):
            statuses.append("synonym_equivalent")
            reasons.append("Atmosphere components normalize to compatible canonical chemical symbols.")
        elif relation == "HAS_RADIUS" and likely_zhwiki_radius_extraction_error(normalized_by_source):
            statuses.append("likely_zhwiki_extraction_error")
            reasons.append("zh_wikipedia radius is orders of magnitude smaller than another source; raw data is not changed.")
        else:
            statuses.append("value_conflict")
            reasons.append(build_conflict_reason(relation, normalized_by_source))
    return {
        "subject": subject,
        "relation": relation,
        "status": statuses,
        "reason": " ".join(reasons),
        "present_sources": present_sources,
        "missing_sources": missing_sources,
        "values_by_source": values_by_source,
        "normalized_by_source": normalized_by_source,
    }


def group_numeric_equivalent(normalized_by_source: Dict[str, List[Dict[str, Any]]]) -> bool:
    numeric_groups = {}
    for source, values in normalized_by_source.items():
        parsed = [item for item in values if item.get("numeric_value") is not None and item.get("normalized_unit")]
        if not parsed:
            return False
        numeric_groups[source] = parsed
    baseline = next(iter(numeric_groups.values()))
    for values in numeric_groups.values():
        if not any(values_equivalent(left, right) for left in baseline for right in values):
            return False
    return True


def group_normalized_equivalent(normalized_by_source: Dict[str, List[Dict[str, Any]]]) -> bool:
    groups = []
    for values in normalized_by_source.values():
        normalized = {str(item.get("normalized_value") or "") for item in values if item.get("normalized_value")}
        if not normalized:
            return False
        groups.append(normalized)
    baseline = groups[0]
    return all(bool(baseline.intersection(group)) for group in groups[1:])


def group_atmosphere_synonym_equivalent(normalized_by_source: Dict[str, List[Dict[str, Any]]]) -> bool:
    groups = []
    for values in normalized_by_source.values():
        components = set()
        for item in values:
            if item.get("normalized_unit") == "component_set":
                components.update(part for part in str(item.get("normalized_value") or "").split(";") if part)
        if not components:
            return False
        groups.append(components)
    baseline = groups[0]
    for group in groups[1:]:
        if not baseline.intersection(group):
            return False
        if not (baseline.issubset(group) or group.issubset(baseline)):
            return False
    return True


def likely_zhwiki_radius_extraction_error(normalized_by_source: Dict[str, List[Dict[str, Any]]]) -> bool:
    zh_values = [
        float(item["numeric_value"])
        for item in normalized_by_source.get("zh_wikipedia", [])
        if item.get("normalized_unit") == "km" and item.get("numeric_value") is not None
    ]
    other_values = [
        float(item["numeric_value"])
        for source, values in normalized_by_source.items()
        if source != "zh_wikipedia"
        for item in values
        if item.get("normalized_unit") == "km" and item.get("numeric_value") is not None
    ]
    if not zh_values or not other_values:
        return False
    largest_other = max(other_values)
    smallest_zh = min(value for value in zh_values if value > 0)
    largest_zh = max(zh_values)
    return (largest_other >= 1000 and smallest_zh < 100) or (largest_other / max(largest_zh, 1e-9) >= 5)


def build_conflict_reason(relation: str, normalized_by_source: Dict[str, List[Dict[str, Any]]]) -> str:
    parse_statuses = {
        source: [item.get("parse_status") for item in values]
        for source, values in normalized_by_source.items()
    }
    if any("unparsed" in statuses for statuses in parse_statuses.values()):
        return f"Values remain different after normalization; at least one source could not be fully parsed for {relation}."
    return f"Values parse successfully but normalized values differ for {relation}."


def classify_key_v3(
    key: Tuple[str, str],
    records_by_source: Dict[str, List[Dict[str, Any]]],
    metadata_keys_with_breaks: set[Tuple[str, str]],
) -> Dict[str, Any]:
    item = classify_key_v2(key, records_by_source, metadata_keys_with_breaks)
    relation = item["relation"]
    statuses = [status for status in item["status"] if status not in {"value_conflict", "likely_zhwiki_extraction_error"}]
    reasons = [item["reason"]] if item.get("reason") else []
    values_by_source = item["values_by_source"]
    normalized_by_source = item["normalized_by_source"]
    if len(item["present_sources"]) >= 2:
        if "exact_match" in statuses or "unit_equivalent" in statuses or "normalized_equivalent" in statuses or "synonym_equivalent" in statuses:
            pass
        elif relation in {"ORBITS", "LOCATED_IN", "PART_OF", "DISCOVERED_BY"} and entity_groups_equivalent(values_by_source):
            statuses.append("entity_alias_equivalent")
            reasons.append("Object values resolve to the same canonical entity alias/QID.")
        elif relation == "HAS_RADIUS" and likely_zhwiki_radius_extraction_error(normalized_by_source):
            statuses.append("likely_zhwiki_extraction_error")
            reasons.append("zh_wikipedia radius is orders of magnitude smaller than another source; raw data is not changed.")
        elif relation == "HAS_RADIUS" and same_quantity_different_radius_kind(records_by_source, normalized_by_source):
            statuses.append("same_quantity_different_measurement_kind")
            statuses.append("radius_kind_mismatch")
            reasons.append("Radius values are compatible with mean/equatorial/polar or other measurement-kind differences, not a direct fact conflict.")
        elif relation == "HAS_MASS" and mass_reference_mismatch(normalized_by_source):
            statuses.append("mass_reference_mismatch")
            reasons.append("Mass values use incompatible reference units or mass scales; needs source-specific interpretation before conflict judgment.")
        elif "likely_zhwiki_extraction_error" in item["status"]:
            statuses.append("likely_zhwiki_extraction_error")
            reasons.append("Inherited v2 extraction-error signal.")
        else:
            statuses.append("value_conflict")
            reasons.append(build_conflict_reason(relation, normalized_by_source))
    item["status"] = ordered_statuses(statuses)
    item["reason"] = " ".join(dict.fromkeys(reason for reason in reasons if reason))
    item["measurement_kinds_by_source"] = {
        source: [measurement_kind_from_record(record) for record in records]
        for source, records in records_by_source.items()
    }
    return item


def ordered_statuses(statuses: List[str]) -> List[str]:
    order = [
        "source_missing",
        "insufficient_metadata",
        "exact_match",
        "unit_equivalent",
        "normalized_equivalent",
        "synonym_equivalent",
        "entity_alias_equivalent",
        "same_quantity_different_measurement_kind",
        "radius_kind_mismatch",
        "mass_reference_mismatch",
        "likely_zhwiki_extraction_error",
        "value_conflict",
    ]
    seen = set()
    result = []
    for status in order:
        if status in statuses and status not in seen:
            seen.add(status)
            result.append(status)
    for status in statuses:
        if status not in seen:
            seen.add(status)
            result.append(status)
    return result


def measurement_kind_from_record(record: Dict[str, Any]) -> str:
    text = " ".join(str(record.get(key, "")) for key in ("raw", "object", "pattern", "table_field")).lower()
    if "赤道" in text or "equatorial" in text:
        return "equatorial_radius"
    if "极半径" in text or "polar" in text:
        return "polar_radius"
    if "平均" in text or "mean radius" in text or "vol. mean" in text:
        return "mean_radius"
    if "distance from sun" in text:
        return "mean_distance_from_sun"
    if "semi-major" in text or "semimajor" in text:
        return "semi_major_axis"
    return "unspecified"


def same_quantity_different_radius_kind(
    records_by_source: Dict[str, List[Dict[str, Any]]],
    normalized_by_source: Dict[str, List[Dict[str, Any]]],
) -> bool:
    values = [
        float(item["numeric_value"])
        for source_values in normalized_by_source.values()
        for item in source_values
        if item.get("normalized_unit") == "km" and item.get("numeric_value") is not None
    ]
    if len(values) < 2:
        return False
    kinds = {
        measurement_kind_from_record(record)
        for records in records_by_source.values()
        for record in records
    }
    spread = (max(values) - min(values)) / max(max(values), 1e-9)
    explicit_kind_mismatch = len(kinds - {"unspecified"}) >= 2
    return spread <= 0.08 and (explicit_kind_mismatch or len(set(round(value, 1) for value in values)) > 1)


def mass_reference_mismatch(normalized_by_source: Dict[str, List[Dict[str, Any]]]) -> bool:
    parse_statuses = {
        str(item.get("parse_status"))
        for values in normalized_by_source.values()
        for item in values
    }
    units = {
        str(item.get("normalized_unit"))
        for values in normalized_by_source.values()
        for item in values
        if item.get("normalized_unit")
    }
    return "unknown_unit" in parse_statuses or len(units) > 1


def collect_relation_semantics_warnings() -> List[Dict[str, Any]]:
    if not os.path.exists(NASA_PREVIEW_REPORT):
        return []
    try:
        with open(NASA_PREVIEW_REPORT, "r", encoding="utf-8") as handle:
            report = json.load(handle)
    except Exception:
        return []
    warnings = []
    for record in report.get("preview", {}).get("sample_records", []):
        for fact in record.get("triples", []):
            if fact.get("relation_semantics_warning"):
                warnings.append({
                    "source": "nasa",
                    "title": record.get("title", ""),
                    "relation": fact.get("relation", ""),
                    "table_field": fact.get("table_field", ""),
                    "derived": bool(fact.get("derived")),
                    "derived_from": fact.get("derived_from", ""),
                    "warning_reason": fact.get("warning_reason", ""),
                })
    return warnings


def build_evidence_packet(finding: Dict[str, Any], records_by_source: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    subject = finding["subject"]
    relation = finding["relation"]
    evidence_values = {}
    for source, records in records_by_source.items():
        evidence_values[source] = []
        for record in records:
            raw_value = record.get("object", "")
            normalized = normalize_value(raw_value, relation)
            kind = infer_measurement_kind(
                relation=relation,
                raw_text=record.get("raw", raw_value),
                source_title=record.get("source_title", record.get("subject", "")),
                source_field=record.get("table_field", record.get("pattern", "")),
            )
            evidence_values[source].append({
                "raw_value": raw_value,
                "normalized_value": normalized.get("normalized_value", ""),
                "unit": normalized.get("normalized_unit", ""),
                "parse_status": normalized.get("parse_status", ""),
                "measurement_kind": kind["measurement_kind"],
                "measurement_confidence": kind["confidence"],
                "measurement_evidence": kind["evidence"],
                "measurement_warning": kind["warning"],
                "source_title": record.get("source_title", ""),
                "source_url": record.get("source_url", ""),
                "source_record_id": record.get("source_record_id", ""),
                "target_file": record.get("_path", ""),
                "target_record_hint": {
                    "subject": record.get("subject", ""),
                    "relation": record.get("relation", ""),
                    "object": record.get("object", ""),
                },
            })
    classification = classify_evidence_packet(subject, relation, evidence_values, finding)
    return {
        "subject": subject,
        "relation": relation,
        "sources_involved": sorted(records_by_source.keys()),
        "values_by_source": finding.get("values_by_source", {}),
        "evidence_by_source": evidence_values,
        "audit_classification": classification["audit_classification"],
        "likely_resolution": classification["likely_resolution"],
        "confidence": classification["confidence"],
        "reason": classification["reason"],
    }


def classify_evidence_packet(
    subject: str,
    relation: str,
    evidence_values: Dict[str, List[Dict[str, Any]]],
    finding: Dict[str, Any],
) -> Dict[str, Any]:
    all_values = [value for values in evidence_values.values() for value in values]
    kinds = {value["measurement_kind"] for value in all_values}
    zhwiki_values = evidence_values.get("zh_wikipedia", [])
    if relation == "ORBITS":
        values_by_source = {
            source: [item["raw_value"] for item in values]
            for source, values in evidence_values.items()
        }
        if entity_groups_equivalent(values_by_source):
            return evidence_class("entity_alias_gap", "add_alias", 0.82, "Orbit targets normalize to the same entity but raw aliases differ.")
        if any(str(value["raw_value"]) in {"地月系", "Earth-Moon system"} for value in all_values):
            return evidence_class("ontology_semantics_mismatch", "no_action_manual_review", 0.74, "Orbit target appears to mix direct host and system-level ontology granularity.")
        return evidence_class("true_value_conflict", "no_action_manual_review", 0.62, "Orbit targets remain different after alias normalization.")
    if relation == "HAS_RADIUS":
        if any(value["unit"] == "km" and numeric_string(value["normalized_value"]) is not None and numeric_string(value["normalized_value"]) < 100 for value in zhwiki_values):
            return evidence_class("zhwiki_extraction_error", "mark_extraction_error", 0.86, "zh_wikipedia radius is implausibly small relative to astronomical body radius context.")
        if len(kinds - {"unknown"}) >= 2 or "radius_kind_mismatch" in finding.get("status", []):
            return evidence_class("measurement_kind_mismatch", "add_measurement_kind", 0.78, "Radius records mix mean/equatorial/polar or unspecified radius kinds.")
    if relation == "HAS_MASS":
        numbers = [numeric_string(value["normalized_value"]) for value in all_values if value["unit"] == "kg"]
        numbers = [number for number in numbers if number is not None and number > 0]
        if len(numbers) >= 2:
            spread = (max(numbers) - min(numbers)) / max(max(numbers), 1e-9)
            if spread <= 0.01:
                return evidence_class("source_granularity_mismatch", "no_action_manual_review", 0.76, "Mass values differ by less than 1%; likely precision/significant-figure or source granularity difference.")
        if any(value["parse_status"] == "unknown_unit" for value in all_values):
            return evidence_class("wikidata_unit_or_qualifier_gap", "normalize_unit", 0.72, "A mass value contains an unmapped unit or qualifier gap.")
    return evidence_class("true_value_conflict", "no_action_manual_review", 0.6, "Values remain materially different after unit, alias, synonym, and measurement-kind checks.")


def evidence_class(audit_classification: str, likely_resolution: str, confidence: float, reason: str) -> Dict[str, Any]:
    return {
        "audit_classification": audit_classification,
        "likely_resolution": likely_resolution,
        "confidence": confidence,
        "reason": reason,
    }


def numeric_string(value: Any) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def build_quality_patch_candidates(evidence_packets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candidates = []
    for index, packet in enumerate(evidence_packets, start=1):
        action = action_for_classification(packet["audit_classification"])
        target_source, target_record = choose_patch_target(packet)
        candidates.append({
            "patch_id": f"source_conflict_v4_{index:03d}",
            "action": action,
            "target_source": target_source,
            "target_file": target_record.get("target_file", ""),
            "target_record_hint": target_record.get("target_record_hint", {}),
            "before": {
                "values_by_source": packet["values_by_source"],
            },
            "after": proposed_after(packet, action),
            "rationale": packet["reason"],
            "confidence": packet["confidence"],
            "requires_human_approval": True,
        })
    return candidates


def action_for_classification(classification: str) -> str:
    return {
        "measurement_kind_mismatch": "add_measurement_kind",
        "zhwiki_extraction_error": "mark_extraction_error",
        "entity_alias_gap": "add_alias",
        "wikidata_unit_or_qualifier_gap": "normalize_unit",
        "source_granularity_mismatch": "no_action_manual_review",
        "ontology_semantics_mismatch": "no_action_manual_review",
        "true_value_conflict": "no_action_manual_review",
    }.get(classification, "no_action_manual_review")


def choose_patch_target(packet: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    if packet["audit_classification"] == "zhwiki_extraction_error" and packet["evidence_by_source"].get("zh_wikipedia"):
        return "zh_wikipedia", packet["evidence_by_source"]["zh_wikipedia"][0]
    for source, values in packet["evidence_by_source"].items():
        if values:
            return source, values[0]
    return "audit", {}


def proposed_after(packet: Dict[str, Any], action: str) -> Dict[str, Any]:
    if action == "add_measurement_kind":
        return {"proposal": "annotate candidate measurement_kind only; do not mutate formal triples"}
    if action == "mark_extraction_error":
        return {"proposal": "mark record as likely extraction error in quality patch candidate only"}
    if action == "add_alias":
        return {"proposal": "add alias mapping in entity_normalizer after human review"}
    if action == "normalize_unit":
        return {"proposal": "add or refine unit_registry mapping after human review"}
    return {"proposal": "manual review; no automatic data change"}


def source_missing_breakdown(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_source = Counter()
    by_relation = Counter()
    by_source_relation = Counter()
    for item in findings:
        if "source_missing" not in item["status"]:
            continue
        relation = item["relation"]
        for source in item["missing_sources"]:
            by_source[source] += 1
            by_relation[relation] += 1
            by_source_relation[f"{source}:{relation}"] += 1
    return {
        "by_source": dict(by_source),
        "by_relation": dict(by_relation),
        "by_source_relation": dict(by_source_relation),
    }


def write_markdown(report: Dict[str, Any]) -> None:
    lines = [
        "# Source Conflict Audit",
        "",
        "This audit is read-only. It compares existing triples in `zh_wikipedia`, `wikidata`, and `nasa`; it does not alter retrieval, fusion, Chroma, Neo4j, or default answers.",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Status Counts", ""])
    for key, value in report["status_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Notable Value Conflicts", ""])
    conflicts = [item for item in report["findings"] if "value_conflict" in item["status"]]
    for item in conflicts[:20]:
        lines.append(f"- `{item['subject']}` / `{item['relation']}`: {json.dumps(item['values_by_source'], ensure_ascii=False)}")
    if not conflicts:
        lines.append("- No value conflicts found among overlapping source keys.")
    lines.extend(["", "## Metadata Issues", ""])
    for item in report["metadata_incomplete"][:20]:
        lines.append(f"- `{item.get('source')}` `{item.get('subject', '')}` / `{item.get('relation', '')}`: {', '.join(item.get('missing_or_invalid', []))}")
    if not report["metadata_incomplete"]:
        lines.append("- No metadata-incomplete records found.")
    lines.extend(["", "## Boundary", ""])
    lines.append("- Audit results are not used for default answer fusion.")
    lines.append("- `ACTIVE_SOURCE` remains `zh_wikipedia`.")
    os.makedirs(os.path.dirname(REPORT_MD), exist_ok=True)
    with open(REPORT_MD, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def write_markdown_v2(report: Dict[str, Any]) -> None:
    lines = [
        "# Source Conflict Audit v2",
        "",
        "This v2 audit is read-only. It normalizes numeric units and atmosphere synonyms for audit reporting only; it does not alter triples, Chroma, Neo4j, retrieval, GUI behavior, or default answers.",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## V1 vs V2", ""])
    comparison = report["v1_v2_comparison"]
    for key, value in comparison.items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Source Missing Breakdown", ""])
    for key, value in report["source_missing_breakdown"]["by_source"].items():
        lines.append(f"- `{key}` missing: {value}")
    lines.extend(["", "## Remaining Value Conflicts", ""])
    conflicts = [item for item in report["findings"] if "value_conflict" in item["status"]]
    for item in conflicts[:40]:
        lines.append(f"- `{item['subject']}` / `{item['relation']}`: {item['reason']} {json.dumps(item['values_by_source'], ensure_ascii=False)}")
    if not conflicts:
        lines.append("- No remaining value conflicts after v2 normalization.")
    lines.extend(["", "## Likely zh_wikipedia Extraction Errors", ""])
    extraction_errors = [item for item in report["findings"] if "likely_zhwiki_extraction_error" in item["status"]]
    for item in extraction_errors[:40]:
        lines.append(f"- `{item['subject']}` / `{item['relation']}`: {json.dumps(item['values_by_source'], ensure_ascii=False)}")
    if not extraction_errors:
        lines.append("- No likely zh_wikipedia extraction errors found.")
    lines.extend(["", "## Boundary", ""])
    lines.append("- Audit results are not used for default answer fusion.")
    lines.append("- `ACTIVE_SOURCE` remains `zh_wikipedia`.")
    os.makedirs(os.path.dirname(REPORT_V2_MD), exist_ok=True)
    with open(REPORT_V2_MD, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def write_markdown_v3(report: Dict[str, Any]) -> None:
    lines = [
        "# Source Conflict Audit v3",
        "",
        "This v3 audit is read-only. It adds Wikidata unit-QID normalization, entity alias/QID normalization, and measurement-kind explanations for audit reporting only.",
        "",
        "## V1/V2/V3 Comparison",
        "",
        "| Metric | V1 | V2 | V3 |",
        "| --- | ---: | ---: | ---: |",
    ]
    comparison = report["v1_v2_v3_comparison"]
    for metric in ("value_conflict", "unit_equivalent", "synonym_equivalent", "entity_alias_equivalent", "same_quantity_different_measurement_kind", "likely_zhwiki_extraction_error"):
        row = comparison.get(metric, {})
        lines.append(f"| `{metric}` | {row.get('v1', 0)} | {row.get('v2', 0)} | {row.get('v3', 0)} |")
    lines.extend(["", "## Entity Alias Equivalent", ""])
    for item in [entry for entry in report["findings"] if "entity_alias_equivalent" in entry["status"]][:40]:
        lines.append(f"- `{item['subject']}` / `{item['relation']}`: {json.dumps(item['values_by_source'], ensure_ascii=False)}")
    lines.extend(["", "## Same Quantity Different Measurement Kind", ""])
    for item in [entry for entry in report["findings"] if "same_quantity_different_measurement_kind" in entry["status"]][:40]:
        lines.append(f"- `{item['subject']}` / `{item['relation']}`: {json.dumps(item['measurement_kinds_by_source'], ensure_ascii=False)}")
    lines.extend(["", "## Remaining True Conflicts", ""])
    conflicts = [entry for entry in report["findings"] if "value_conflict" in entry["status"]]
    for item in conflicts[:40]:
        lines.append(f"- `{item['subject']}` / `{item['relation']}`: {item['reason']} {json.dumps(item['values_by_source'], ensure_ascii=False)}")
    if not conflicts:
        lines.append("- No remaining value conflicts after v3 normalization.")
    lines.extend(["", "## zh_wikipedia Extraction Errors", ""])
    for item in [entry for entry in report["findings"] if "likely_zhwiki_extraction_error" in entry["status"]][:40]:
        lines.append(f"- `{item['subject']}` / `{item['relation']}`: {json.dumps(item['values_by_source'], ensure_ascii=False)}")
    lines.extend(["", "## NASA Relation Semantics Warnings", ""])
    for warning in report["relation_semantics_warnings"]:
        lines.append(f"- `{warning['title']}` / `{warning['relation']}` from `{warning['table_field']}`: {warning['warning_reason']}")
    if not report["relation_semantics_warnings"]:
        lines.append("- No NASA relation semantics warnings found.")
    lines.extend(["", "## Boundary", ""])
    lines.append("- Audit results are not used for default answer fusion.")
    lines.append("- `ACTIVE_SOURCE` remains `zh_wikipedia`.")
    os.makedirs(os.path.dirname(REPORT_V3_MD), exist_ok=True)
    with open(REPORT_V3_MD, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def write_markdown_v4(report: Dict[str, Any]) -> None:
    lines = [
        "# Source Conflict Audit v4",
        "",
        "This v4 audit creates evidence packets and candidate quality patches only. It does not mutate formal triples, Chroma, Neo4j, GUI behavior, or default answers.",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Evidence Packets", ""])
    for packet in report["evidence_packets"]:
        lines.append(f"- `{packet['subject']}` / `{packet['relation']}`: `{packet['audit_classification']}`; {packet['likely_resolution']}; confidence `{packet['confidence']}`")
    lines.extend(["", "## Candidate Patches", ""])
    for candidate in report["quality_patch_candidates"]:
        lines.append(f"- `{candidate['patch_id']}` `{candidate['action']}` -> `{candidate['target_source']}`; approval required `{candidate['requires_human_approval']}`")
    lines.extend(["", "## Boundary", ""])
    lines.append("- Candidate patches are not applied.")
    lines.append("- `ACTIVE_SOURCE` remains `zh_wikipedia`.")
    os.makedirs(os.path.dirname(REPORT_V4_MD), exist_ok=True)
    with open(REPORT_V4_MD, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def run_audit() -> Dict[str, Any]:
    records_by_source = {source: load_source_triples(source) for source in SOURCES}
    metadata_incomplete = []
    for source, records in records_by_source.items():
        metadata_incomplete.extend(metadata_breaks(source, records))

    index = build_index(records_by_source)
    findings = [classify_key(key, source_records) for key, source_records in sorted(index.items())]
    status_counts = Counter(status for item in findings for status in item["status"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": list(SOURCES),
        "summary": {
            "total_records": sum(len(records) for records in records_by_source.values()),
            "total_subject_relation_keys": len(index),
            "metadata_incomplete_count": len(metadata_incomplete),
            "value_conflict_count": status_counts.get("value_conflict", 0),
            "exact_match_count": status_counts.get("exact_match", 0),
            "unit_equivalent_count": status_counts.get("unit_equivalent", 0),
            "source_missing_count": status_counts.get("source_missing", 0),
        },
        "status_counts": dict(status_counts),
        "findings": findings,
        "metadata_incomplete": metadata_incomplete,
        "boundary": {
            "read_only": True,
            "default_answer_fusion": False,
            "active_source_changed": False,
        },
        "outputs": {
            "json": REPORT_JSON,
            "markdown": REPORT_MD,
        },
    }
    os.makedirs(os.path.dirname(REPORT_JSON), exist_ok=True)
    with open(REPORT_JSON, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    write_markdown(report)
    return report


def run_audit_v2(v1_report: Dict[str, Any] | None = None) -> Dict[str, Any]:
    records_by_source = {source: load_source_triples(source) for source in SOURCES}
    metadata_incomplete = []
    for source, records in records_by_source.items():
        metadata_incomplete.extend(metadata_breaks(source, records))
    metadata_keys_with_breaks = {
        (str(item.get("subject", "")).strip(), str(item.get("relation", "")).strip())
        for item in metadata_incomplete
        if item.get("subject") and item.get("relation")
    }
    index = build_index(records_by_source)
    findings = [
        classify_key_v2(key, source_records, metadata_keys_with_breaks)
        for key, source_records in sorted(index.items())
    ]
    status_counts = Counter(status for item in findings for status in item["status"])
    v1_counts = (v1_report or {}).get("status_counts", {})
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": list(SOURCES),
        "version": "v2_value_normalized",
        "summary": {
            "total_records": sum(len(records) for records in records_by_source.values()),
            "total_subject_relation_keys": len(index),
            "metadata_incomplete_count": len(metadata_incomplete),
            "insufficient_metadata_count": status_counts.get("insufficient_metadata", 0),
            "value_conflict_count": status_counts.get("value_conflict", 0),
            "likely_zhwiki_extraction_error_count": status_counts.get("likely_zhwiki_extraction_error", 0),
            "exact_match_count": status_counts.get("exact_match", 0),
            "unit_equivalent_count": status_counts.get("unit_equivalent", 0),
            "normalized_equivalent_count": status_counts.get("normalized_equivalent", 0),
            "synonym_equivalent_count": status_counts.get("synonym_equivalent", 0),
            "source_missing_count": status_counts.get("source_missing", 0),
        },
        "status_counts": dict(status_counts),
        "source_missing_breakdown": source_missing_breakdown(findings),
        "v1_v2_comparison": {
            "v1_value_conflict_count": v1_counts.get("value_conflict", 0),
            "v2_value_conflict_count": status_counts.get("value_conflict", 0),
            "v2_unit_equivalent_count": status_counts.get("unit_equivalent", 0),
            "v2_normalized_equivalent_count": status_counts.get("normalized_equivalent", 0),
            "v2_synonym_equivalent_count": status_counts.get("synonym_equivalent", 0),
            "v2_likely_zhwiki_extraction_error_count": status_counts.get("likely_zhwiki_extraction_error", 0),
        },
        "findings": findings,
        "metadata_incomplete": metadata_incomplete,
        "boundary": {
            "read_only": True,
            "default_answer_fusion": False,
            "active_source_changed": False,
        },
        "outputs": {
            "json": REPORT_V2_JSON,
            "markdown": REPORT_V2_MD,
        },
    }
    os.makedirs(os.path.dirname(REPORT_V2_JSON), exist_ok=True)
    with open(REPORT_V2_JSON, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    write_markdown_v2(report)
    return report


def run_audit_v3(v1_report: Dict[str, Any] | None = None, v2_report: Dict[str, Any] | None = None) -> Dict[str, Any]:
    records_by_source = {source: load_source_triples(source) for source in SOURCES}
    metadata_incomplete = []
    for source, records in records_by_source.items():
        metadata_incomplete.extend(metadata_breaks(source, records))
    metadata_keys_with_breaks = {
        (str(item.get("subject", "")).strip(), str(item.get("relation", "")).strip())
        for item in metadata_incomplete
        if item.get("subject") and item.get("relation")
    }
    index = build_index(records_by_source)
    findings = [
        classify_key_v3(key, source_records, metadata_keys_with_breaks)
        for key, source_records in sorted(index.items())
    ]
    status_counts = Counter(status for item in findings for status in item["status"])
    v1_counts = (v1_report or {}).get("status_counts", {})
    v2_counts = (v2_report or {}).get("status_counts", {})
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": list(SOURCES),
        "version": "v3_unit_entity_measurement_normalized",
        "summary": {
            "total_records": sum(len(records) for records in records_by_source.values()),
            "total_subject_relation_keys": len(index),
            "metadata_incomplete_count": len(metadata_incomplete),
            "insufficient_metadata_count": status_counts.get("insufficient_metadata", 0),
            "value_conflict_count": status_counts.get("value_conflict", 0),
            "entity_alias_equivalent_count": status_counts.get("entity_alias_equivalent", 0),
            "same_quantity_different_measurement_kind_count": status_counts.get("same_quantity_different_measurement_kind", 0),
            "radius_kind_mismatch_count": status_counts.get("radius_kind_mismatch", 0),
            "mass_reference_mismatch_count": status_counts.get("mass_reference_mismatch", 0),
            "likely_zhwiki_extraction_error_count": status_counts.get("likely_zhwiki_extraction_error", 0),
            "exact_match_count": status_counts.get("exact_match", 0),
            "unit_equivalent_count": status_counts.get("unit_equivalent", 0),
            "normalized_equivalent_count": status_counts.get("normalized_equivalent", 0),
            "synonym_equivalent_count": status_counts.get("synonym_equivalent", 0),
            "source_missing_count": status_counts.get("source_missing", 0),
        },
        "status_counts": dict(status_counts),
        "source_missing_breakdown": source_missing_breakdown(findings),
        "relation_semantics_warnings": collect_relation_semantics_warnings(),
        "v1_v2_v3_comparison": {
            key: {
                "v1": v1_counts.get(key, 0),
                "v2": v2_counts.get(key, 0),
                "v3": status_counts.get(key, 0),
            }
            for key in (
                "value_conflict",
                "unit_equivalent",
                "synonym_equivalent",
                "entity_alias_equivalent",
                "same_quantity_different_measurement_kind",
                "likely_zhwiki_extraction_error",
            )
        },
        "findings": findings,
        "metadata_incomplete": metadata_incomplete,
        "boundary": {
            "read_only": True,
            "default_answer_fusion": False,
            "active_source_changed": False,
        },
        "outputs": {
            "json": REPORT_V3_JSON,
            "markdown": REPORT_V3_MD,
        },
    }
    os.makedirs(os.path.dirname(REPORT_V3_JSON), exist_ok=True)
    with open(REPORT_V3_JSON, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    write_markdown_v3(report)
    return report


def run_audit_v4(v3_report: Dict[str, Any] | None = None) -> Dict[str, Any]:
    records_by_source = {source: load_source_triples(source) for source in SOURCES}
    metadata_incomplete = []
    for source, records in records_by_source.items():
        metadata_incomplete.extend(metadata_breaks(source, records))
    index = build_index(records_by_source)
    findings = (v3_report or {}).get("findings", [])
    remaining_conflicts = [finding for finding in findings if "value_conflict" in finding.get("status", [])]
    evidence_packets = [
        build_evidence_packet(finding, index[(finding["subject"], finding["relation"])])
        for finding in remaining_conflicts
        if (finding["subject"], finding["relation"]) in index
    ]
    candidates = build_quality_patch_candidates(evidence_packets)
    os.makedirs(QUALITY_PATCH_DIR, exist_ok=True)
    with open(QUALITY_PATCH_CANDIDATES, "w", encoding="utf-8") as handle:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "source_conflict_audit_v4",
            "apply_supported": False,
            "candidates": candidates,
        }, handle, ensure_ascii=False, indent=2)
    classification_counts = Counter(packet["audit_classification"] for packet in evidence_packets)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "v4_conflict_resolution_candidates",
        "summary": {
            "metadata_incomplete_count": len(metadata_incomplete),
            "evidence_packet_count": len(evidence_packets),
            "quality_patch_candidate_count": len(candidates),
            "requires_human_approval_count": sum(1 for candidate in candidates if candidate["requires_human_approval"]),
        },
        "v3_value_conflict_count": len(remaining_conflicts),
        "classification_counts": dict(classification_counts),
        "evidence_packets": evidence_packets,
        "quality_patch_candidates": candidates,
        "quality_patch_output": QUALITY_PATCH_CANDIDATES,
        "boundary": {
            "read_only": True,
            "candidate_patches_applied": False,
            "default_answer_fusion": False,
            "active_source_changed": False,
        },
        "outputs": {
            "json": REPORT_V4_JSON,
            "markdown": REPORT_V4_MD,
        },
    }
    os.makedirs(os.path.dirname(REPORT_V4_JSON), exist_ok=True)
    with open(REPORT_V4_JSON, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    write_markdown_v4(report)
    return report


def main() -> None:
    configure_stdout()
    v1_report = run_audit()
    v2_report = run_audit_v2(v1_report)
    v3_report = run_audit_v3(v1_report, v2_report)
    v4_report = run_audit_v4(v3_report)
    print(json.dumps({
        "v1": {
            "summary": v1_report["summary"],
            "outputs": v1_report["outputs"],
        },
        "v2": {
            "summary": v2_report["summary"],
            "status_counts": v2_report["status_counts"],
            "v1_v2_comparison": v2_report["v1_v2_comparison"],
            "outputs": v2_report["outputs"],
        },
        "v3": {
            "summary": v3_report["summary"],
            "status_counts": v3_report["status_counts"],
            "v1_v2_v3_comparison": v3_report["v1_v2_v3_comparison"],
            "relation_semantics_warning_count": len(v3_report["relation_semantics_warnings"]),
            "outputs": v3_report["outputs"],
        },
        "v4": {
            "summary": v4_report["summary"],
            "classification_counts": v4_report["classification_counts"],
            "quality_patch_output": v4_report["quality_patch_output"],
            "outputs": v4_report["outputs"],
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

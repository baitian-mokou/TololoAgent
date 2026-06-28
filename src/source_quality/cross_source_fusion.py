from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

from src.source_quality.measurement_kind import infer_measurement_kind
from src.source_quality.value_normalizer import normalize_value, values_equivalent


DEFAULT_RELATIVE_THRESHOLDS = {
    "HAS_RADIUS": 0.01,
    "HAS_MASS": 0.02,
    "DISTANCE": 0.02,
    "ORBITAL_DISTANCE": 0.02,
}


def _relative_threshold(relation: str) -> float:
    return float(DEFAULT_RELATIVE_THRESHOLDS.get(str(relation or "").strip(), 0.01))


def _relative_difference(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    max_value = max(values)
    min_value = min(values)
    denominator = max(abs(max_value), abs(min_value), 1e-12)
    return abs(max_value - min_value) / denominator


def _measurement_kind(record: Dict[str, Any]) -> Dict[str, Any]:
    return infer_measurement_kind(
        relation=str(record.get("relation", "")).strip(),
        raw_text=record.get("object", ""),
        source_title=record.get("source_title", ""),
        source_field=record.get("source_field", ""),
    )


def _group_records(records: List[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        subject = str(record.get("subject", "")).strip()
        relation = str(record.get("relation", "")).strip()
        if subject and relation:
            grouped[(subject, relation)].append(dict(record))
    return grouped


def _merged_agreement_record(records: List[Dict[str, Any]], normalized: List[Dict[str, Any]]) -> Dict[str, Any]:
    first = dict(records[0])
    evidence_by_source = {}
    sources = []
    for record, item in zip(records, normalized):
        source_name = str(record.get("source_name") or record.get("source") or "").strip()
        if not source_name:
            continue
        sources.append(source_name)
        evidence_by_source[source_name] = {
            "raw_value": record.get("object", ""),
            "normalized_value": item.get("normalized_value", ""),
            "normalized_unit": item.get("normalized_unit", ""),
        }
    first["fusion_status"] = "multi_source_agreement"
    first["sources"] = sorted(set(sources))
    first["source_count"] = len(set(sources))
    first["evidence_by_source"] = evidence_by_source
    return first


def _review_candidate(subject: str, relation: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
    values = []
    for record in records:
        values.append({
            "object": str(record.get("object", "")).strip(),
            "sources": [str(record.get("source_name") or record.get("source") or "").strip()],
        })
    return {
        "subject": subject,
        "relation": relation,
        "values": values,
    }


def fuse_cross_source_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = {
        "multi_source_agreement_count": 0,
        "near_equivalent_values_count": 0,
        "measurement_kind_difference_count": 0,
        "human_review_required_count": 0,
    }
    fused_records: List[Dict[str, Any]] = []
    review_candidates: List[Dict[str, Any]] = []

    for (subject, relation), items in _group_records(records).items():
        normalized = [normalize_value(item.get("object", ""), relation) for item in items]
        if len(items) >= 2 and all(
            values_equivalent(normalized[0], current, rel_tol=1e-9) for current in normalized[1:]
        ):
            summary["multi_source_agreement_count"] += 1
            fused_records.append(_merged_agreement_record(items, normalized))
            continue

        measurement_kinds = [_measurement_kind(item) for item in items]
        known_kinds = {
            str(info.get("measurement_kind", "")).strip()
            for info in measurement_kinds
            if str(info.get("measurement_kind", "")).strip() not in {"", "unknown"}
        }
        if len(known_kinds) >= 2:
            summary["measurement_kind_difference_count"] += 1
            for record, info in zip(items, measurement_kinds):
                merged = dict(record)
                merged["fusion_status"] = "same_quantity_different_measurement_kind"
                merged["measurement_kind"] = info.get("measurement_kind", "unknown")
                fused_records.append(merged)
            continue

        numeric_values = [item.get("numeric_value") for item in normalized]
        if len(items) >= 2 and all(value is not None for value in numeric_values):
            rel_diff = _relative_difference([float(value) for value in numeric_values])
            if rel_diff <= _relative_threshold(relation):
                summary["near_equivalent_values_count"] += 1
                for record in items:
                    merged = dict(record)
                    merged["fusion_status"] = "near_equivalent_values"
                    merged["requires_human_review"] = False
                    fused_records.append(merged)
                continue

        if len(items) >= 2:
            summary["human_review_required_count"] += 1
            review_candidates.append(_review_candidate(subject, relation, items))
            for record in items:
                merged = dict(record)
                merged["fusion_status"] = "human_review_required"
                merged["requires_human_review"] = True
                fused_records.append(merged)
            continue

        single = dict(items[0])
        single["fusion_status"] = "single_source_only"
        single["requires_human_review"] = False
        fused_records.append(single)

    return {
        "summary": summary,
        "fused_records": fused_records,
        "review_candidates": review_candidates,
    }

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.source_adapters.nasa import NASA_FACT_SHEETS, NasaPipelineAdapter
from src.source_adapters.wikidata import WikidataFixtureAdapter
from src.source_quality.entity_normalizer import normalize_entity
from src.source_quality.value_normalizer import normalize_value, values_equivalent


REMAINING_PATCH_IDS = (
    "source_conflict_v4_001",
    "source_conflict_v4_003",
    "source_conflict_v4_004",
    "source_conflict_v4_005",
    "source_conflict_v4_007",
    "source_conflict_v4_008",
)

CANDIDATES_JSON = os.path.join(PROJECT_ROOT, "data", "quality_patches", "source_conflict_resolution_candidates.json")
AUDIT_V4_JSON = os.path.join(PROJECT_ROOT, "evaluation", "source_conflict_audit_v4.json")
REPORT_JSON = os.path.join(PROJECT_ROOT, "evaluation", "external_source_review.json")
REPORT_MD = os.path.join(PROJECT_ROOT, "docs", "external_source_review.md")
ORBITS_REVIEW_MD = os.path.join(PROJECT_ROOT, "docs", "orbits_ontology_review.md")
REVIEW_CANDIDATES_JSON = os.path.join(PROJECT_ROOT, "data", "quality_patches", "external_source_review_candidates.json")

FetchResult = Dict[str, Any]
EvidenceFetcher = Callable[[str, str], FetchResult]


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def remaining_candidates(candidates_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_id = {item.get("patch_id"): item for item in candidates_payload.get("candidates", [])}
    return [by_id[patch_id] for patch_id in REMAINING_PATCH_IDS if patch_id in by_id]


def audit_packets_by_patch_id(audit_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    packets = audit_payload.get("evidence_packets", [])
    by_key = {(packet.get("subject"), packet.get("relation")): packet for packet in packets}
    output: Dict[str, Dict[str, Any]] = {}
    for candidate in audit_payload.get("quality_patch_candidates", []):
        patch_id = str(candidate.get("patch_id") or "")
        hint = candidate.get("target_record_hint", {})
        packet = by_key.get((hint.get("subject"), hint.get("relation")))
        if patch_id and packet:
            output[patch_id] = packet
    return output


def fetch_external_evidence(subject: str, relation: str) -> FetchResult:
    errors: List[Dict[str, str]] = []
    facts: List[Dict[str, Any]] = []

    try:
        wikidata = WikidataFixtureAdapter(mode="live", entity=subject)
        raw_payload = wikidata.fetch_live()
        for record in wikidata.normalize_records(raw_payload):
            for fact in record.get("triples", []):
                if fact.get("relation") == relation:
                    payload = dict(fact)
                    payload["evidence_source"] = "wikidata_live_preview"
                    payload["title"] = record.get("title", subject)
                    facts.append(payload)
    except Exception as exc:  # live preview must not break the review flow
        errors.append({"source": "wikidata_live_preview", "error": str(exc)})

    if subject in NASA_FACT_SHEETS:
        try:
            nasa = NasaPipelineAdapter(mode="live", entity=subject)
            raw_payload = nasa.fetch_live()
            for record in nasa.normalize_records(raw_payload):
                for fact in record.get("triples", []):
                    if fact.get("relation") == relation:
                        payload = dict(fact)
                        payload["evidence_source"] = "nasa_live_preview"
                        payload["title"] = record.get("title", subject)
                        facts.append(payload)
        except Exception as exc:
            errors.append({"source": "nasa_live_preview", "error": str(exc)})

    return {"facts": facts, "errors": errors}


def build_review(
    *,
    candidates_path: str = CANDIDATES_JSON,
    audit_path: str = AUDIT_V4_JSON,
    fetcher: EvidenceFetcher = fetch_external_evidence,
) -> Dict[str, Any]:
    candidates_payload = load_json(candidates_path)
    audit_payload = load_json(audit_path)
    packets_by_patch_id = audit_packets_by_patch_id(audit_payload)
    records = []

    for candidate in remaining_candidates(candidates_payload):
        patch_id = str(candidate["patch_id"])
        hint = candidate.get("target_record_hint", {})
        subject = str(hint.get("subject") or "")
        relation = str(hint.get("relation") or "")
        packet = packets_by_patch_id.get(patch_id, {})
        current_values = candidate.get("before", {}).get("values_by_source", {})
        fetch_result = safe_fetch(fetcher, subject, relation)
        external_facts = fetch_result.get("facts", [])
        record = classify_review_record(
            patch_id=patch_id,
            subject=subject,
            relation=relation,
            current_values_by_source=current_values,
            packet=packet,
            external_facts=external_facts,
            fetch_errors=fetch_result.get("errors", []),
        )
        records.append(record)

    summary = summarize_records(records)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "P8_external_source_conflict_review",
        "remaining_patch_ids": list(REMAINING_PATCH_IDS),
        "summary": summary,
        "records": records,
        "boundary": {
            "read_only": True,
            "formal_triples_written": False,
            "chroma_written": False,
            "neo4j_written": False,
            "patches_applied": False,
            "requires_human_approval_for_all_candidates": True,
        },
        "outputs": {
            "json": REPORT_JSON,
            "markdown": REPORT_MD,
            "orbits_ontology_review": ORBITS_REVIEW_MD,
            "candidate_patches": REVIEW_CANDIDATES_JSON,
        },
    }


def safe_fetch(fetcher: EvidenceFetcher, subject: str, relation: str) -> FetchResult:
    try:
        result = fetcher(subject, relation)
    except Exception as exc:
        return {"facts": [], "errors": [{"source": "external_fetcher", "error": str(exc)}]}
    return {
        "facts": list(result.get("facts", [])),
        "errors": list(result.get("errors", [])),
    }


def classify_review_record(
    *,
    patch_id: str,
    subject: str,
    relation: str,
    current_values_by_source: Dict[str, List[str]],
    packet: Dict[str, Any],
    external_facts: List[Dict[str, Any]],
    fetch_errors: List[Dict[str, str]],
) -> Dict[str, Any]:
    if patch_id == "source_conflict_v4_003" and relation == "ORBITS":
        return classify_orbits_record(
            patch_id,
            subject,
            relation,
            current_values_by_source,
            packet,
            external_facts,
            fetch_errors,
        )

    external_fact = choose_external_fact(external_facts, relation)
    comparison_result = "unresolved"
    recommendation = "defer_unresolved"
    confidence = 0.35
    normalized_external_value = ""
    evidence_source = ""
    evidence_url = ""
    source_record_id = ""

    if external_fact:
        normalized_external_value = str(external_fact.get("normalized_value") or external_fact.get("object") or "")
        evidence_source = str(external_fact.get("evidence_source") or external_fact.get("source_name") or "")
        evidence_url = str(external_fact.get("source_url") or "")
        source_record_id = str(external_fact.get("source_record_id") or "")
        comparison_result, recommendation, confidence = compare_external_to_current(
            relation,
            normalized_external_value,
            current_values_by_source,
        )
    elif packet.get("audit_classification") == "source_granularity_mismatch":
        comparison_result = "confirms_precision_difference"
        recommendation = "mark_precision_difference"
        confidence = float(packet.get("confidence") or 0.7)

    if is_likely_zhwiki_numeric_extraction_error(relation, current_values_by_source):
        comparison_result = "likely_zhwiki_extraction_error"
        recommendation = "mark_extraction_error"
        confidence = max(confidence, 0.78)

    return {
        "patch_id": patch_id,
        "subject": subject,
        "relation": relation,
        "current_values_by_source": current_values_by_source,
        "external_evidence": external_fact or {},
        "evidence_source": evidence_source,
        "evidence_url": evidence_url,
        "source_record_id": source_record_id,
        "normalized_external_value": normalized_external_value,
        "comparison_result": comparison_result,
        "recommendation": recommendation,
        "confidence": confidence,
        "fetch_errors": fetch_errors,
        "requires_human_approval": True,
    }


def classify_orbits_record(
    patch_id: str,
    subject: str,
    relation: str,
    current_values_by_source: Dict[str, List[str]],
    packet: Dict[str, Any],
    external_facts: List[Dict[str, Any]],
    fetch_errors: List[Dict[str, str]],
) -> Dict[str, Any]:
    zh_values = current_values_by_source.get("zh_wikipedia", [])
    wikidata_values = current_values_by_source.get("wikidata", [])
    bad_zh_values = [value for value in zh_values if not is_known_celestial_entity(value)]
    wikidata_entity_values = [value for value in wikidata_values if is_known_celestial_entity(value)]

    comparison_result = "ontology_rule_needed"
    recommendation = "add_ontology_constraint_candidate"
    confidence = 0.86 if bad_zh_values and wikidata_entity_values else 0.68
    if bad_zh_values:
        recommendation = "mark_extraction_error"

    external_fact = choose_external_fact(external_facts, relation)
    return {
        "patch_id": patch_id,
        "subject": subject,
        "relation": relation,
        "current_values_by_source": current_values_by_source,
        "external_evidence": external_fact or {
            "ontology_observation": "ORBITS should point to a known celestial-body entity; descriptive phrases are not valid orbit targets.",
            "zh_wikipedia_invalid_objects": bad_zh_values,
            "wikidata_entity_objects": wikidata_entity_values,
            "audit_reason": packet.get("reason", ""),
        },
        "evidence_source": str((external_fact or {}).get("evidence_source") or "v4_audit_ontology_review"),
        "evidence_url": str((external_fact or {}).get("source_url") or ""),
        "source_record_id": str((external_fact or {}).get("source_record_id") or ""),
        "normalized_external_value": str((external_fact or {}).get("normalized_value") or ""),
        "comparison_result": comparison_result,
        "recommendation": recommendation,
        "confidence": confidence,
        "fetch_errors": fetch_errors,
        "requires_human_approval": True,
    }


def choose_external_fact(facts: List[Dict[str, Any]], relation: str) -> Dict[str, Any]:
    for fact in facts:
        if fact.get("relation") == relation:
            return fact
    return {}


def compare_external_to_current(
    relation: str,
    external_value: str,
    current_values_by_source: Dict[str, List[str]],
) -> tuple[str, str, float]:
    external_normalized = normalize_value(external_value, relation)
    source_scores: Dict[str, bool] = {}
    for source, values in current_values_by_source.items():
        source_scores[source] = any(values_equivalent(external_normalized, normalize_value(value, relation), rel_tol=0.01) for value in values)

    if source_scores.get("wikidata") and not source_scores.get("zh_wikipedia"):
        return "confirms_wikidata", "add_external_evidence", 0.8
    if source_scores.get("zh_wikipedia") and not source_scores.get("wikidata"):
        return "confirms_zh_wikipedia", "add_external_evidence", 0.74
    if source_scores.get("zh_wikipedia") and source_scores.get("wikidata"):
        return "confirms_precision_difference", "mark_precision_difference", 0.76
    return "unresolved", "defer_unresolved", 0.4


def is_likely_zhwiki_numeric_extraction_error(relation: str, values_by_source: Dict[str, List[str]]) -> bool:
    if relation not in {"HAS_MASS", "HAS_RADIUS"}:
        return False
    zh_values = values_by_source.get("zh_wikipedia", [])
    wikidata_values = values_by_source.get("wikidata", [])
    for zh_value in zh_values:
        zh = normalize_value(zh_value, relation)
        for wikidata_value in wikidata_values:
            wd = normalize_value(wikidata_value, relation)
            if zh.get("numeric_value") and wd.get("numeric_value"):
                ratio = max(float(zh["numeric_value"]), float(wd["numeric_value"])) / max(min(float(zh["numeric_value"]), float(wd["numeric_value"])), 1e-30)
                if ratio >= 100.0:
                    return True
    return False


def is_known_celestial_entity(value: Any) -> bool:
    normalized = normalize_entity(value)
    return bool(normalized.get("canonical_id")) and normalized.get("parse_status") != "unmapped_entity"


def summarize_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    recommendations: Dict[str, int] = {}
    for record in records:
        counts[record["comparison_result"]] = counts.get(record["comparison_result"], 0) + 1
        recommendations[record["recommendation"]] = recommendations.get(record["recommendation"], 0) + 1
    return {
        "reviewed_conflict_count": len(records),
        "comparison_result_counts": counts,
        "recommendation_counts": recommendations,
        "requires_human_approval_count": sum(1 for record in records if record.get("requires_human_approval") is True),
    }


def build_candidate_patches(report: Dict[str, Any]) -> Dict[str, Any]:
    candidates = []
    action_by_recommendation = {
        "mark_extraction_error": "mark_extraction_error",
        "add_external_evidence": "add_external_evidence",
        "add_ontology_constraint_candidate": "add_ontology_constraint_candidate",
        "mark_precision_difference": "mark_precision_difference",
        "defer_unresolved": "defer_unresolved",
    }
    for record in report["records"]:
        candidates.append({
            "patch_id": f"external_review_{record['patch_id']}",
            "source_patch_id": record["patch_id"],
            "subject": record["subject"],
            "relation": record["relation"],
            "action": action_by_recommendation.get(record["recommendation"], "defer_unresolved"),
            "comparison_result": record["comparison_result"],
            "recommendation": record["recommendation"],
            "before": {"values_by_source": record["current_values_by_source"]},
            "after": {"proposal": "candidate only; no formal triples change without human approval"},
            "external_evidence": record["external_evidence"],
            "confidence": record["confidence"],
            "requires_human_approval": True,
            "safe_to_apply": False,
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "external_source_review",
        "apply_supported": False,
        "candidates": candidates,
        "boundary": {
            "formal_triples_written": False,
            "patches_applied": False,
            "all_candidates_require_human_approval": all(item["requires_human_approval"] for item in candidates),
            "all_candidates_safe_to_apply": all(item["safe_to_apply"] for item in candidates),
        },
    }


def write_markdown(report: Dict[str, Any], path: str = REPORT_MD) -> None:
    lines = [
        "# P8 External Source Review",
        "",
        f"Generated at: {report['generated_at']}",
        "",
        "This is a preview/audit report only. It does not apply patches, write Chroma, write Neo4j, or mutate formal triples.",
        "",
        "## Summary",
        "",
        f"- Reviewed conflicts: {report['summary']['reviewed_conflict_count']}",
        f"- Requires human approval: {report['summary']['requires_human_approval_count']}",
        f"- Comparison results: `{json.dumps(report['summary']['comparison_result_counts'], ensure_ascii=False)}`",
        f"- Recommendations: `{json.dumps(report['summary']['recommendation_counts'], ensure_ascii=False)}`",
        "",
        "## Records",
        "",
    ]
    for record in report["records"]:
        lines.extend([
            f"### {record['patch_id']} {record['subject']} / {record['relation']}",
            "",
            f"- comparison_result: `{record['comparison_result']}`",
            f"- recommendation: `{record['recommendation']}`",
            f"- confidence: {record['confidence']}",
            f"- requires_human_approval: `{record['requires_human_approval']}`",
            f"- current_values_by_source: `{json.dumps(record['current_values_by_source'], ensure_ascii=False)}`",
            f"- evidence_source: `{record['evidence_source']}`",
            f"- evidence_url/source_record_id: `{record['evidence_url'] or record['source_record_id']}`",
            f"- fetch_errors: `{json.dumps(record['fetch_errors'], ensure_ascii=False)}`",
            "",
        ])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")


def write_orbits_review(path: str = ORBITS_REVIEW_MD) -> None:
    lines = [
        "# ORBITS Ontology Review",
        "",
        "Scope: preview-only ontology review for `月球 / ORBITS`. No ontology or triple files are modified.",
        "",
        "## Finding",
        "",
        "The current conflict is not a simple value disagreement. `wikidata` gives `地球`, which is a known celestial entity and a plausible direct orbit target for the Moon. `zh_wikipedia` gives `太阳系内密度第二高`, which is a descriptive phrase rather than an orbit target.",
        "",
        "## Interpretation",
        "",
        "- ORBITS should normally mean direct orbital parent, not a free-text descriptive statement.",
        "- The `zh_wikipedia` object is best treated as an extraction error candidate.",
        "- The ontology should add object validation for ORBITS instead of silently accepting descriptive phrases.",
        "",
        "## Candidate Rules",
        "",
        "- ORBITS object must be a known celestial-body entity or an accepted entity alias/QID.",
        "- Descriptive phrases are invalid ORBITS objects.",
        "- Failed ORBITS object validation should mark the record as `extraction_error_candidate`.",
        "",
        "No formal ontology change is applied in this phase.",
        "",
    ]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def run_review(
    *,
    candidates_path: str = CANDIDATES_JSON,
    audit_path: str = AUDIT_V4_JSON,
    report_json: str = REPORT_JSON,
    report_md: str = REPORT_MD,
    orbits_md: str = ORBITS_REVIEW_MD,
    review_candidates_json: str = REVIEW_CANDIDATES_JSON,
    fetcher: EvidenceFetcher = fetch_external_evidence,
) -> Dict[str, Any]:
    report = build_review(candidates_path=candidates_path, audit_path=audit_path, fetcher=fetcher)
    report["outputs"] = {
        "json": report_json,
        "markdown": report_md,
        "orbits_ontology_review": orbits_md,
        "candidate_patches": review_candidates_json,
    }
    dump_json(report_json, report)
    write_markdown(report, report_md)
    write_orbits_review(orbits_md)
    dump_json(review_candidates_json, build_candidate_patches(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run preview-only external source review for remaining conflict patches.")
    parser.add_argument("--candidates", default=CANDIDATES_JSON)
    parser.add_argument("--audit", default=AUDIT_V4_JSON)
    parser.add_argument("--output", default=REPORT_JSON)
    parser.add_argument("--markdown", default=REPORT_MD)
    parser.add_argument("--orbits-review", default=ORBITS_REVIEW_MD)
    parser.add_argument("--review-candidates", default=REVIEW_CANDIDATES_JSON)
    args = parser.parse_args()
    report = run_review(
        candidates_path=args.candidates,
        audit_path=args.audit,
        report_json=args.output,
        report_md=args.markdown,
        orbits_md=args.orbits_review,
        review_candidates_json=args.review_candidates,
    )
    print(json.dumps({
        "passed": True,
        "reviewed_conflict_count": report["summary"]["reviewed_conflict_count"],
        "outputs": report["outputs"],
        "formal_triples_written": report["boundary"]["formal_triples_written"],
    }, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

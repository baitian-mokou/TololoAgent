from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import BASE_DIR


QUALITY_REVIEW_DIR = Path(BASE_DIR) / "data" / "quality_review"
DEFAULT_CANDIDATES = Path(BASE_DIR) / "data" / "quality_patches" / "source_conflict_resolution_candidates.json"
DEFAULT_AUDIT = Path(BASE_DIR) / "evaluation" / "source_conflict_audit_v4.json"
DEFAULT_EXTERNAL_CANDIDATES = Path(BASE_DIR) / "data" / "quality_patches" / "external_source_review_candidates.json"
DEFAULT_QUEUE = QUALITY_REVIEW_DIR / "quality_review_queue.json"
DEFAULT_DECISIONS = QUALITY_REVIEW_DIR / "quality_review_decisions.json"

ALLOWED_DECISIONS = {"pending", "approved", "rejected", "deferred"}


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _as_list(payload: Any, *keys: str) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _packet_key(subject: str, relation: str) -> Tuple[str, str]:
    return (str(subject or "").strip(), str(relation or "").strip())


def build_audit_packet_index(audit_payload: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    packets = _as_list(audit_payload, "evidence_packets")
    return {_packet_key(item.get("subject"), item.get("relation")): item for item in packets}


def values_from_candidate(candidate: Dict[str, Any], source: str) -> List[Any]:
    return list(candidate.get("before", {}).get("values_by_source", {}).get(source, []))


def current_value(candidate: Dict[str, Any]) -> Any:
    values = values_from_candidate(candidate, "zh_wikipedia")
    if values:
        return values if len(values) > 1 else values[0]
    hint = candidate.get("target_record_hint", {})
    return hint.get("object", "")


def proposed_payload(candidate: Dict[str, Any], issue_type: str) -> Tuple[Any, Dict[str, Any], str]:
    action = candidate.get("action") or candidate.get("likely_resolution") or "manual_review"
    after = candidate.get("after", {})
    if action == "add_measurement_kind" or issue_type == "measurement_kind_mismatch":
        return None, {
            "action": "add_measurement_kind",
            "measurement_kind": "unspecified_radius",
            "quality_status": "approved_metadata_only",
            "note": after.get("proposal") or "只补充测量口径元数据，不修改正式事实值。",
        }, "metadata_only"
    proposed = candidate.get("proposed_value")
    if proposed is None and isinstance(after, dict):
        proposed = after.get("proposed_value") or after.get("proposal")
    change_type = "value_change" if proposed and "no automatic data change" not in str(proposed) else "manual_review"
    return proposed, {}, change_type


def risk_level(issue_type: str, change_type: str, confidence: Any) -> str:
    if change_type == "value_change" or issue_type == "true_value_conflict":
        return "high"
    if issue_type == "source_granularity_mismatch":
        return "medium"
    if issue_type == "measurement_kind_mismatch":
        return "low"
    try:
        if float(confidence) < 0.7:
            return "medium"
    except (TypeError, ValueError):
        pass
    return "medium"


def system_recommendation(issue_type: str, action: str, change_type: str) -> str:
    if action == "add_measurement_kind" or change_type == "metadata_only":
        return "建议只补充元数据标注，不修改 subject/relation/object 正式事实值。"
    if issue_type == "source_granularity_mismatch":
        return "建议拒绝自动修复；这更像来源精度或粒度差异，保留复查记录即可。"
    if issue_type == "true_value_conflict":
        return "建议暂缓；需要外部权威来源或人工确认后才能考虑正式改值。"
    return "建议人工复核；默认不自动写入正式三元组。"


def external_review_summary(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "external_patch_id": candidate.get("patch_id"),
        "source_patch_id": candidate.get("source_patch_id"),
        "action": candidate.get("action"),
        "comparison_result": candidate.get("comparison_result"),
        "recommendation": candidate.get("recommendation"),
        "confidence": candidate.get("confidence"),
        "requires_human_approval": candidate.get("requires_human_approval", True),
        "safe_to_apply": candidate.get("safe_to_apply", False),
        "values_by_source": candidate.get("before", {}).get("values_by_source", {}),
        "proposal": candidate.get("after", {}).get("proposal", ""),
        "external_evidence": candidate.get("external_evidence", {}),
    }


def build_external_review_index(external_payload: Any) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    by_source_patch: Dict[str, Dict[str, Any]] = {}
    independent: List[Dict[str, Any]] = []
    for candidate in _as_list(external_payload, "candidates", "items"):
        source_patch_id = candidate.get("source_patch_id")
        if source_patch_id:
            by_source_patch[source_patch_id] = external_review_summary(candidate)
        else:
            independent.append(candidate)
    return by_source_patch, independent


def source_evidence(
    candidate: Dict[str, Any],
    packet: Optional[Dict[str, Any]],
    external_review: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    evidence = {
        "values_by_source": candidate.get("before", {}).get("values_by_source", {}),
        "target_source": candidate.get("target_source", "zh_wikipedia"),
        "target_file": candidate.get("target_file", ""),
        "target_record_hint": candidate.get("target_record_hint", {}),
    }
    if packet:
        evidence["sources_involved"] = packet.get("sources_involved", [])
        evidence["evidence_by_source"] = packet.get("evidence_by_source", {})
        evidence["audit_reason"] = packet.get("reason", "")
    if external_review:
        evidence["external_review"] = external_review
    return evidence


def external_recommendation_text(external_review: Optional[Dict[str, Any]]) -> str:
    if not external_review:
        return ""
    recommendation = external_review.get("recommendation") or external_review.get("action")
    comparison = external_review.get("comparison_result") or "unresolved"
    confidence = external_review.get("confidence")
    return f" 外部复核：{recommendation}（{comparison}，confidence={confidence}），仍需人工审批后才能处理。"


def existing_decisions_by_patch(path: Path) -> Dict[str, Dict[str, Any]]:
    payload = load_json(path, default={}) or {}
    decisions = _as_list(payload, "decisions")
    return {item.get("patch_id"): item for item in decisions if item.get("patch_id")}


def existing_items_by_patch(path: Path) -> Dict[str, Dict[str, Any]]:
    payload = load_json(path, default={}) or {}
    items = _as_list(payload, "items")
    return {item.get("patch_id"): item for item in items if item.get("patch_id")}


def build_queue_items(
    candidates_payload: Dict[str, Any],
    audit_payload: Dict[str, Any],
    existing_decisions: Dict[str, Dict[str, Any]],
    existing_items: Dict[str, Dict[str, Any]],
    external_payload: Any = None,
    generated_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    generated_at = generated_at or utc_now()
    packet_index = build_audit_packet_index(audit_payload)
    external_by_patch, independent_external = build_external_review_index(external_payload)
    used_review_ids = set()
    items: List[Dict[str, Any]] = []

    base_candidates = [
        ("source_conflict_resolution_candidates", item)
        for item in _as_list(candidates_payload, "candidates", "quality_patch_candidates")
    ]
    for item in independent_external:
        base_candidates.append(("external_source_review_candidates", item))

    for source_name, candidate in base_candidates:
        patch_id = candidate.get("patch_id") or candidate.get("id")
        if not patch_id:
            continue
        hint = candidate.get("target_record_hint", {})
        subject = candidate.get("subject") or hint.get("subject", "")
        relation = candidate.get("relation") or hint.get("relation", "")
        packet = packet_index.get(_packet_key(subject, relation))
        issue_type = (
            candidate.get("classification")
            or candidate.get("audit_classification")
            or (packet or {}).get("audit_classification")
            or "manual_review"
        )
        proposed_value, proposed_metadata, change_type = proposed_payload(candidate, issue_type)
        action = candidate.get("action") or (packet or {}).get("likely_resolution") or "manual_review"
        external_review = external_by_patch.get(patch_id)
        risk = risk_level(issue_type, change_type, candidate.get("confidence"))
        prior_item = existing_items.get(patch_id, {})
        prior_decision = existing_decisions.get(patch_id, {})
        decision = prior_decision.get("human_decision") or prior_item.get("human_decision") or "pending"
        if decision not in ALLOWED_DECISIONS:
            decision = "pending"
        base_review_id = prior_item.get("review_id") or prior_decision.get("review_id") or f"qr_{patch_id}"
        review_id = base_review_id
        suffix = 2
        while review_id in used_review_ids:
            review_id = f"{base_review_id}_{suffix}"
            suffix += 1
        used_review_ids.add(review_id)

        safe = change_type == "metadata_only" and risk in {"low", "medium"}
        item = {
            "review_id": review_id,
            "patch_id": patch_id,
            "subject": subject,
            "relation": relation,
            "current_value": current_value(candidate),
            "proposed_value": proposed_value,
            "proposed_metadata": proposed_metadata,
            "issue_type": issue_type,
            "risk_level": risk,
            "source_evidence": source_evidence(candidate, packet, external_review),
            "review_evidence": {
                "audit_v4": source_evidence(candidate, packet),
                "external_source_review": external_review,
            },
            "system_recommendation": system_recommendation(issue_type, action, change_type) + external_recommendation_text(external_review),
            "human_decision": decision,
            "safe_to_apply": safe,
            "change_type": change_type,
            "action": action,
            "target_file": candidate.get("target_file", ""),
            "target_record_hint": hint,
            "source_queue": source_name,
            "merged_external_review": bool(external_review),
            "created_at": prior_item.get("created_at") or generated_at,
            "updated_at": generated_at,
        }
        items.append(item)
    return items


def build_decisions_payload(items: List[Dict[str, Any]], existing_decisions: Dict[str, Dict[str, Any]], generated_at: str) -> Dict[str, Any]:
    decisions = []
    for item in items:
        prior = existing_decisions.get(item["patch_id"], {})
        human_decision = prior.get("human_decision", "pending")
        if human_decision not in ALLOWED_DECISIONS:
            human_decision = "pending"
        safe_to_apply = bool(prior.get("safe_to_apply")) if human_decision == "approved" else False
        decisions.append(
            {
                "review_id": item["review_id"],
                "patch_id": item["patch_id"],
                "subject": item["subject"],
                "relation": item["relation"],
                "issue_type": item["issue_type"],
                "risk_level": item["risk_level"],
                "change_type": item["change_type"],
                "human_decision": human_decision,
                "human_reason": prior.get("human_reason", ""),
                "approved_action": prior.get("approved_action") if human_decision == "approved" else None,
                "safe_to_apply": safe_to_apply,
                "reviewed_by": prior.get("reviewed_by", ""),
                "reviewed_at": prior.get("reviewed_at", ""),
                "updated_at": prior.get("updated_at") or generated_at,
            }
        )
    return {
        "schema_version": "quality_review_decisions_v1",
        "queue_path": "data/quality_review/quality_review_queue.json",
        "decision_policy": {
            "no_item_is_approved_by_default": True,
            "approved_requires_human_reason": True,
            "formal_data_write_allowed_by_default": False,
            "writes_chroma_or_neo4j": False,
        },
        "decisions": decisions,
    }


def build_quality_review_queue(
    candidates_path: str = str(DEFAULT_CANDIDATES),
    audit_path: str = str(DEFAULT_AUDIT),
    external_candidates_path: str = str(DEFAULT_EXTERNAL_CANDIDATES),
    queue_path: str = str(DEFAULT_QUEUE),
    decisions_path: str = str(DEFAULT_DECISIONS),
) -> Dict[str, Any]:
    generated_at = utc_now()
    candidates = load_json(Path(candidates_path), default={}) or {}
    audit = load_json(Path(audit_path), default={}) or {}
    external = load_json(Path(external_candidates_path), default=None)
    existing_decisions = existing_decisions_by_patch(Path(decisions_path))
    existing_items = existing_items_by_patch(Path(queue_path))

    items = build_queue_items(candidates, audit, existing_decisions, existing_items, external, generated_at)
    queue = {
        "schema_version": "quality_review_queue_v1",
        "generated_at": generated_at,
        "inputs": {
            "candidates": str(Path(candidates_path)),
            "audit": str(Path(audit_path)),
            "external_candidates": str(Path(external_candidates_path)) if Path(external_candidates_path).exists() else None,
        },
        "summary": {
            "item_count": len(items),
            "pending_count": sum(1 for item in items if item.get("human_decision") == "pending"),
            "approved_count": sum(1 for item in items if item.get("human_decision") == "approved"),
            "high_risk_count": sum(1 for item in items if item.get("risk_level") == "high"),
            "metadata_only_count": sum(1 for item in items if item.get("change_type") == "metadata_only"),
            "value_change_count": sum(1 for item in items if item.get("change_type") == "value_change"),
            "merged_external_review_count": sum(1 for item in items if item.get("merged_external_review")),
        },
        "items": items,
    }
    decisions = build_decisions_payload(items, existing_decisions, generated_at)
    dump_json(Path(queue_path), queue)
    dump_json(Path(decisions_path), decisions)
    return {
        "queue_path": str(queue_path),
        "decisions_path": str(decisions_path),
        "item_count": len(items),
        "pending_count": queue["summary"]["pending_count"],
        "approved_count": queue["summary"]["approved_count"],
    }


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Build the human quality review queue without applying any data changes.")
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT))
    parser.add_argument("--external-candidates", default=str(DEFAULT_EXTERNAL_CANDIDATES))
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--decisions", default=str(DEFAULT_DECISIONS))
    args = parser.parse_args()
    result = build_quality_review_queue(
        candidates_path=args.candidates,
        audit_path=args.audit,
        external_candidates_path=args.external_candidates,
        queue_path=args.queue,
        decisions_path=args.decisions,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

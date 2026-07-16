from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, BASE_DIR, SOURCE_REGISTRY


DEFAULT_QUEUE = Path(BASE_DIR) / "data" / "quality_review" / "quality_review_queue.json"
DEFAULT_DECISIONS = Path(BASE_DIR) / "data" / "quality_review" / "quality_review_decisions.json"
DEFAULT_OUTPUT = Path(BASE_DIR) / "evaluation" / "validated_revision_candidates.json"


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def display_value(value: Any, unit: str = "") -> str:
    text = str(value or "").strip()
    unit = str(unit or "").strip()
    if unit and unit not in text:
        return f"{text} {unit}"
    return text


def values_for_zh_source(item: Dict[str, Any]) -> Any:
    values = item.get("source_evidence", {}).get("values_by_source", {}).get("zh_wikipedia", [])
    if values:
        return values if len(values) > 1 else values[0]
    return item.get("current_value")


def build_candidates(queue_items: List[Dict[str, Any]], decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    item_by_patch = {item.get("patch_id"): item for item in queue_items if item.get("patch_id")}
    candidates = []
    for decision in decisions:
        proposed_value = str(decision.get("user_proposed_value", "")).strip()
        if not proposed_value:
            continue
        item = item_by_patch.get(decision.get("patch_id"), {})
        risk_level = decision.get("risk_level") or item.get("risk_level")
        evidence_note = decision.get("user_evidence_note", "")
        reason = decision.get("user_revision_reason", "")
        needs_extra_source = risk_level == "high" and not decision.get("user_evidence_url")
        suggest_validated = bool(reason.strip()) and not needs_extra_source
        candidates.append({
            "review_id": decision.get("review_id") or item.get("review_id"),
            "patch_id": decision.get("patch_id"),
            "subject": decision.get("subject") or item.get("subject"),
            "relation": decision.get("relation") or item.get("relation"),
            "original_value": values_for_zh_source(item),
            "proposed_value": display_value(proposed_value, decision.get("user_proposed_unit", "")),
            "risk_level": risk_level,
            "revision_status": decision.get("revision_status", "none"),
            "human_decision": decision.get("human_decision", "pending"),
            "safe_to_apply": bool(decision.get("safe_to_apply")),
            "evidence_note": evidence_note,
            "evidence_url": decision.get("user_evidence_url", ""),
            "revision_reason": reason,
            "needs_extra_source": needs_extra_source,
            "recommend_enter_validated": suggest_validated,
            "validation_note": (
                "建议先补充权威来源 URL，再考虑 validated。"
                if needs_extra_source
                else "可由人工显式标记为 validated；不会自动 approve。"
            ),
        })
    return candidates


def prepare_validated_revisions(
    *,
    decisions_path: str = str(DEFAULT_DECISIONS),
    queue_path: str = str(DEFAULT_QUEUE),
    output_path: str = str(DEFAULT_OUTPUT),
    mark_validated: List[str] | None = None,
) -> Dict[str, Any]:
    mark_validated = mark_validated or []
    decisions_file = Path(decisions_path)
    queue_file = Path(queue_path)
    decisions_payload = load_json(decisions_file)
    queue_payload = load_json(queue_file)
    decisions = [item for item in decisions_payload.get("decisions", []) if isinstance(item, dict)]
    queue_items = [item for item in queue_payload.get("items", []) if isinstance(item, dict)]
    marked = []
    errors = []

    if mark_validated:
        patch_ids = {item.get("patch_id"): item for item in decisions if item.get("patch_id")}
        for patch_id in mark_validated:
            decision = patch_ids.get(patch_id)
            if not decision:
                errors.append({"patch_id": patch_id, "error": "decision_not_found"})
                continue
            if not str(decision.get("user_proposed_value", "")).strip():
                errors.append({"patch_id": patch_id, "error": "missing_user_proposed_value"})
                continue
            decision["revision_status"] = "validated"
            decision["updated_at"] = datetime.now(timezone.utc).isoformat()
            marked.append(patch_id)
        if marked:
            dump_json(decisions_file, decisions_payload)

    candidates = build_candidates(queue_items, decisions)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decisions_path": str(decisions_file),
        "queue_path": str(queue_file),
        "candidate_count": len(candidates),
        "marked_validated": marked,
        "auto_approved": False,
        "formal_triples_written": False,
        "formal_data_written": False,
        "chroma_written": False,
        "neo4j_written": False,
        "active_source": ACTIVE_SOURCE,
        "source_registry": SOURCE_REGISTRY,
        "candidates": candidates,
        "errors": errors,
    }
    dump_json(Path(output_path), report)
    return report


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Prepare a report for user revision validation without auto-approval.")
    parser.add_argument("--decisions", default=str(DEFAULT_DECISIONS))
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--mark-validated", nargs="*", default=[])
    args = parser.parse_args()
    report = prepare_validated_revisions(
        decisions_path=args.decisions,
        queue_path=args.queue,
        output_path=args.output,
        mark_validated=args.mark_validated,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report["errors"] else 0)


if __name__ == "__main__":
    main()

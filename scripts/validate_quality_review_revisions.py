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
DEFAULT_OUTPUT = Path(BASE_DIR) / "evaluation" / "quality_review_revision_validation.json"

ALLOWED_REVISION_STATUSES = {"none", "draft", "proposed", "validated", "rejected"}


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


def _items(payload: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    value = payload.get(key, [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def validate_quality_review_revisions(
    decisions_path: str = str(DEFAULT_DECISIONS),
    queue_path: str = str(DEFAULT_QUEUE),
    output_path: str = str(DEFAULT_OUTPUT),
) -> Dict[str, Any]:
    decisions_payload = load_json(Path(decisions_path))
    queue_payload = load_json(Path(queue_path))
    decisions = _items(decisions_payload, "decisions")
    queue_items = _items(queue_payload, "items")
    item_by_patch = {item.get("patch_id"): item for item in queue_items if item.get("patch_id")}
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    status_counts = {status: 0 for status in sorted(ALLOWED_REVISION_STATUSES)}
    revision_count = 0

    for decision in decisions:
        patch_id = decision.get("patch_id")
        item = item_by_patch.get(patch_id, {})
        status = decision.get("revision_status") or "none"
        if status not in ALLOWED_REVISION_STATUSES:
            errors.append({
                "check": "invalid_revision_status",
                "patch_id": patch_id,
                "actual": status,
                "allowed": sorted(ALLOWED_REVISION_STATUSES),
            })
            status = "none"
        status_counts[status] += 1

        proposed_value = str(decision.get("user_proposed_value", "")).strip()
        reason = str(decision.get("user_revision_reason", "")).strip()
        has_revision = bool(proposed_value)
        if has_revision:
            revision_count += 1
        if proposed_value and not reason and status != "draft":
            errors.append({"check": "revision_value_requires_reason_or_draft", "patch_id": patch_id})
        if proposed_value and not reason and status == "draft":
            warnings.append({"check": "draft_revision_missing_reason", "patch_id": patch_id})
        if not proposed_value and status in {"draft", "proposed", "validated"}:
            errors.append({"check": "revision_status_requires_user_proposed_value", "patch_id": patch_id, "revision_status": status})
        if proposed_value and status == "none":
            errors.append({"check": "revision_value_requires_revision_status", "patch_id": patch_id})
        if status == "proposed":
            warnings.append({"check": "proposed_revision_preview_only_by_default", "patch_id": patch_id})
        if status == "validated":
            if decision.get("human_decision") != "approved":
                warnings.append({"check": "validated_revision_waiting_for_approved_decision", "patch_id": patch_id})
            if decision.get("safe_to_apply") is not True:
                warnings.append({"check": "validated_revision_waiting_for_safe_to_apply_true", "patch_id": patch_id})
        if item.get("risk_level") == "high" and has_revision and decision.get("safe_to_apply") is True and status != "validated":
            errors.append({"check": "high_risk_revision_must_not_be_safe_to_apply_before_validation", "patch_id": patch_id})

    source_registry_ok = (
        ACTIVE_SOURCE == "zh_wikipedia"
        and SOURCE_REGISTRY.get("zh_wikipedia") == "active"
        and all(SOURCE_REGISTRY.get(source) == "disabled" for source in ("wikidata", "nasa", "esa"))
    )
    if not source_registry_ok:
        errors.append({"check": "active_source_boundary", "active_source": ACTIVE_SOURCE})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": not errors,
        "decisions_path": decisions_path,
        "queue_path": queue_path,
        "decision_count": len(decisions),
        "queue_item_count": len(item_by_patch),
        "revision_count": revision_count,
        "revision_status_counts": status_counts,
        "proposed_revision_default_apply_blocked": True,
        "formal_triples_written": False,
        "formal_data_written": False,
        "chroma_written": False,
        "neo4j_written": False,
        "active_source": ACTIVE_SOURCE,
        "source_registry": SOURCE_REGISTRY,
        "errors": errors,
        "warnings": warnings,
    }
    dump_json(Path(output_path), report)
    return report


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Validate quality review revision proposals without applying data changes.")
    parser.add_argument("--decisions", default=str(DEFAULT_DECISIONS))
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = validate_quality_review_revisions(args.decisions, args.queue, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

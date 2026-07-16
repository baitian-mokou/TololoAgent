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
from scripts.apply_quality_patches import (
    duplicate_preflight_info,
    load_json,
    load_review_items,
    preview_value_matches,
    target_file_for_item,
    values_for_zh_source,
)


DEFAULT_DECISIONS = Path(BASE_DIR) / "data" / "quality_review" / "quality_review_decisions.json"
DEFAULT_QUEUE = Path(BASE_DIR) / "data" / "quality_review" / "quality_review_queue.json"
DEFAULT_OUTPUT = Path(BASE_DIR) / "evaluation" / "revision_value_change_preflight.json"


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def decisions_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    value = payload.get("decisions", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def proposed_value_for_decision(decision: Dict[str, Any]) -> str:
    value = str(decision.get("user_proposed_value", "")).strip()
    unit = str(decision.get("user_proposed_unit", "")).strip()
    if unit and unit not in value:
        return f"{value} {unit}"
    return value


def build_preflight_item(item: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    proposed_value = proposed_value_for_decision(decision)
    target_file = target_file_for_item(item)
    records = load_json(target_file)
    if not isinstance(records, list):
        raise ValueError(f"{target_file}: target file is not a list of triples")
    matched_records = preview_value_matches(item, records)
    duplicate_info = duplicate_preflight_info(item, records, matched_records, proposed_value)
    original_values = [record.get("object") for record in matched_records]
    if not original_values:
        values = values_for_zh_source(item)
        original_values = values if isinstance(values, list) else [values]
    return {
        "patch_id": decision.get("patch_id"),
        "review_id": decision.get("review_id") or item.get("review_id"),
        "subject": decision.get("subject") or item.get("subject"),
        "relation": decision.get("relation") or item.get("relation"),
        "revision_status": decision.get("revision_status", "none"),
        "human_decision": decision.get("human_decision", "pending"),
        "safe_to_apply": bool(decision.get("safe_to_apply")),
        "target_file": target_file,
        "original_values": original_values,
        "proposed_value": proposed_value,
        "matched_record_count": len(matched_records),
        "matched_records": matched_records,
        **duplicate_info,
    }


def preflight_revision_value_changes(
    *,
    decisions_path: str = str(DEFAULT_DECISIONS),
    queue_path: str = str(DEFAULT_QUEUE),
    output_path: str = str(DEFAULT_OUTPUT),
) -> Dict[str, Any]:
    decisions_payload = load_json(str(decisions_path))
    review_items, _legacy = load_review_items(str(queue_path))
    item_by_patch = {item.get("patch_id"): item for item in review_items if item.get("patch_id")}
    rows = []
    errors = []
    for decision in decisions_from_payload(decisions_payload):
        if not str(decision.get("user_proposed_value", "")).strip():
            continue
        patch_id = decision.get("patch_id")
        item = item_by_patch.get(patch_id)
        if not item:
            errors.append({"patch_id": patch_id, "error": "review_item_not_found"})
            continue
        try:
            rows.append(build_preflight_item(item, decision))
        except Exception as exc:
            errors.append({"patch_id": patch_id, "error": str(exc)})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decisions_path": str(decisions_path),
        "queue_path": str(queue_path),
        "preflight_count": len(rows),
        "duplicate_risk_count": sum(1 for row in rows if row.get("would_create_duplicate")),
        "items": rows,
        "formal_triples_written": False,
        "formal_data_written": False,
        "chroma_written": False,
        "neo4j_written": False,
        "active_source": ACTIVE_SOURCE,
        "source_registry": SOURCE_REGISTRY,
        "errors": errors,
    }
    dump_json(Path(output_path), report)
    return report


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Preflight user revision value changes without writing triples.")
    parser.add_argument("--decisions", default=str(DEFAULT_DECISIONS))
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = preflight_revision_value_changes(
        decisions_path=args.decisions,
        queue_path=args.queue,
        output_path=args.output,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report["errors"] else 0)


if __name__ == "__main__":
    main()

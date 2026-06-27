from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import BASE_DIR


APPROVED_PATCH_ID = "source_conflict_v4_002"
DEFAULT_DECISIONS = os.path.join(BASE_DIR, "data", "quality_patches", "source_conflict_resolution_decisions.recommended.json")
DEFAULT_CANDIDATES = os.path.join(BASE_DIR, "data", "quality_patches", "source_conflict_resolution_candidates.json")
DEFAULT_REPORT = os.path.join(BASE_DIR, "evaluation", "quality_patch_apply_preview.json")
EXPECTED_TARGET_FILE = os.path.join(BASE_DIR, "data", "triples", "天王星_triples.json")
EXPECTED_SUBJECT = "天王星"
EXPECTED_RELATION = "HAS_RADIUS"
EXPECTED_ACTION = "add_measurement_kind"
ANNOTATION = {
    "measurement_kind": "unspecified_radius",
    "quality_status": "approved_metadata_only",
    "quality_patch_id": APPROVED_PATCH_ID,
    "quality_annotation": {
        "classification": "measurement_kind_mismatch",
        "rationale": "Radius records mix mean/equatorial/polar or unspecified radius kinds; formal fact value was not changed.",
        "formal_value_changed": False,
        "reviewed_decision_source": "source_conflict_resolution_decisions.recommended.json",
    },
}


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def select_by_patch_id(items: List[Dict[str, Any]], patch_id: str) -> Dict[str, Any]:
    matches = [item for item in items if item.get("patch_id") == patch_id]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {patch_id}, got {len(matches)}")
    return matches[0]


def validate_approved_patch(decision: Dict[str, Any], candidate: Dict[str, Any]) -> List[str]:
    errors = []
    if decision.get("human_decision") != "approved":
        errors.append("human_decision must be approved")
    if decision.get("safe_to_apply") is not True:
        errors.append("safe_to_apply must be true")
    if decision.get("approved_action") != EXPECTED_ACTION:
        errors.append("approved_action must be add_measurement_kind")
    if candidate.get("action") != EXPECTED_ACTION:
        errors.append("candidate action must be add_measurement_kind")
    if candidate.get("patch_id") != APPROVED_PATCH_ID or decision.get("patch_id") != APPROVED_PATCH_ID:
        errors.append("only source_conflict_v4_002 can be applied")
    return errors


def apply_quality_patch(
    *,
    decisions_path: str = DEFAULT_DECISIONS,
    candidates_path: str = DEFAULT_CANDIDATES,
    report_path: str = DEFAULT_REPORT,
    apply: bool = False,
) -> Dict[str, Any]:
    errors: List[str] = []
    dry_run = not apply
    decisions_payload = load_json(decisions_path)
    candidates_payload = load_json(candidates_path)
    decision = select_by_patch_id(decisions_payload.get("decisions", []), APPROVED_PATCH_ID)
    candidate = select_by_patch_id(candidates_payload.get("candidates", []), APPROVED_PATCH_ID)
    errors.extend(validate_approved_patch(decision, candidate))

    target_file = candidate.get("target_file") or EXPECTED_TARGET_FILE
    if os.path.abspath(target_file) != os.path.abspath(EXPECTED_TARGET_FILE):
        errors.append(f"target_file must be {EXPECTED_TARGET_FILE}")
    expected_values = set(candidate.get("before", {}).get("values_by_source", {}).get("zh_wikipedia", []))
    if expected_values != {"4km", "20km"}:
        errors.append("candidate zh_wikipedia values must be exactly 4km and 20km")

    records = load_json(target_file) if not errors else []
    original_records = deepcopy(records)
    matched_records = []
    changed_records = []

    for index, record in enumerate(records if isinstance(records, list) else []):
        obj = record.get("object")
        if obj in expected_values and (record.get("subject") != EXPECTED_SUBJECT or record.get("relation") != EXPECTED_RELATION):
            errors.append(f"Matched candidate object at index {index} but subject/relation is not 天王星/HAS_RADIUS")
        if record.get("subject") == EXPECTED_SUBJECT and record.get("relation") == EXPECTED_RELATION and obj in expected_values:
            matched_records.append({
                "index": index,
                "subject": record.get("subject"),
                "relation": record.get("relation"),
                "object": obj,
            })
            updated = deepcopy(record)
            updated.update(ANNOTATION)
            if updated.get("subject") != record.get("subject") or updated.get("relation") != record.get("relation") or updated.get("object") != record.get("object"):
                errors.append(f"Formal value changed while preparing record {index}")
            if updated != record:
                changed_records.append({
                    "index": index,
                    "before_keys": sorted(record.keys()),
                    "after_keys": sorted(updated.keys()),
                })
                records[index] = updated

    if not matched_records:
        errors.append("No matching 天王星/HAS_RADIUS records found for 4km/20km")

    formal_values_changed = formal_values_differ(original_records, records)
    if formal_values_changed:
        errors.append("subject/relation/object changed; refusing to apply")

    patches_applied = 0
    if apply and not errors:
        dump_json(target_file, records)
        patches_applied = 1 if changed_records else 0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "apply": bool(apply),
        "patch_id": APPROVED_PATCH_ID,
        "target_file": target_file,
        "matched_records": matched_records,
        "changed_records": changed_records,
        "formal_values_changed": formal_values_changed,
        "patches_applied": patches_applied,
        "errors": errors,
    }
    dump_json(report_path, report)
    if errors:
        raise RuntimeError("; ".join(errors))
    return report


def formal_values_differ(before: List[Dict[str, Any]], after: List[Dict[str, Any]]) -> bool:
    if len(before) != len(after):
        return True
    for left, right in zip(before, after):
        for key in ("subject", "relation", "object"):
            if left.get(key) != right.get(key):
                return True
    return False


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Apply approved quality metadata patches. Defaults to dry-run.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only. This is the default.")
    mode.add_argument("--apply", action="store_true", help="Write approved metadata-only patch.")
    parser.add_argument("--decisions", default=DEFAULT_DECISIONS)
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = apply_quality_patch(
        decisions_path=args.decisions,
        candidates_path=args.candidates,
        report_path=args.report,
        apply=args.apply,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import BASE_DIR


DEFAULT_DECISIONS = os.path.join(BASE_DIR, "data", "quality_review", "quality_review_decisions.json")
DEFAULT_CANDIDATES = os.path.join(BASE_DIR, "data", "quality_review", "quality_review_queue.json")
DEFAULT_REPORT = os.path.join(BASE_DIR, "evaluation", "quality_review_apply_report.json")
DEFAULT_BACKUP_ROOT = os.path.join(BASE_DIR, "data", "backups", "quality_review")

# Kept for older focused tests that monkey-patch this path.
EXPECTED_TARGET_FILE = os.path.join(BASE_DIR, "data", "triples", "天王星_triples.json")

APPROVED_DECISION = "approved"
NON_APPLY_DECISIONS = {"pending", "rejected", "deferred"}


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
        handle.write("\n")


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("items", "candidates", "quality_patch_candidates"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _decisions(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    value = payload.get("decisions", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _legacy_candidate_to_item(candidate: Dict[str, Any]) -> Dict[str, Any]:
    hint = candidate.get("target_record_hint", {})
    action = candidate.get("action") or "manual_review"
    change_type = "metadata_only" if action == "add_measurement_kind" else "manual_review"
    return {
        "review_id": f"qr_{candidate.get('patch_id')}",
        "patch_id": candidate.get("patch_id"),
        "subject": hint.get("subject", "天王星" if action == "add_measurement_kind" else ""),
        "relation": hint.get("relation", "HAS_RADIUS" if action == "add_measurement_kind" else ""),
        "issue_type": "measurement_kind_mismatch" if action == "add_measurement_kind" else "manual_review",
        "risk_level": "low" if change_type == "metadata_only" else "medium",
        "change_type": change_type,
        "action": action,
        "target_file": candidate.get("target_file") or EXPECTED_TARGET_FILE,
        "target_record_hint": hint,
        "source_evidence": {
            "values_by_source": candidate.get("before", {}).get("values_by_source", {}),
            "target_record_hint": hint,
        },
        "proposed_value": None,
        "proposed_metadata": {
            "measurement_kind": "unspecified_radius",
            "quality_status": "approved_metadata_only",
        } if change_type == "metadata_only" else {},
        "safe_to_apply": change_type == "metadata_only",
    }


def load_review_items(path: str) -> Tuple[List[Dict[str, Any]], bool]:
    payload = load_json(path)
    items = _items(payload)
    legacy = "items" not in payload
    if legacy:
        return [_legacy_candidate_to_item(item) for item in items], True
    return items, False


def values_for_zh_source(item: Dict[str, Any]) -> List[Any]:
    evidence = item.get("source_evidence", {})
    values = evidence.get("values_by_source", {}).get("zh_wikipedia", [])
    if values:
        return list(values)
    hint_object = item.get("target_record_hint", {}).get("object")
    return [hint_object] if hint_object else []


def target_file_for_item(item: Dict[str, Any]) -> str:
    return item.get("target_file") or item.get("source_evidence", {}).get("target_file") or EXPECTED_TARGET_FILE


def formal_values_differ(before: List[Dict[str, Any]], after: List[Dict[str, Any]]) -> bool:
    if len(before) != len(after):
        return True
    for left, right in zip(before, after):
        for key in ("subject", "relation", "object"):
            if left.get(key) != right.get(key):
                return True
    return False


def metadata_annotation(item: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    metadata = dict(item.get("proposed_metadata") or {})
    metadata.setdefault("measurement_kind", "unspecified_radius")
    metadata.setdefault("quality_status", "approved_metadata_only")
    metadata["quality_patch_id"] = item.get("patch_id")
    metadata["quality_review_id"] = item.get("review_id")
    metadata["quality_annotation"] = {
        "classification": item.get("issue_type"),
        "rationale": decision.get("human_reason") or item.get("system_recommendation", ""),
        "formal_value_changed": False,
        "reviewed_decision_source": "quality_review_decisions.json",
    }
    return metadata


def prepare_metadata_change(
    item: Dict[str, Any],
    decision: Dict[str, Any],
    records: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
    errors: List[str] = []
    updated_records = deepcopy(records)
    original_records = deepcopy(records)
    expected_values = set(values_for_zh_source(item))
    subject = item.get("subject")
    relation = item.get("relation")
    annotation = metadata_annotation(item, decision)
    matched_records = []
    changed_records = []

    for index, record in enumerate(updated_records):
        if not isinstance(record, dict):
            continue
        if record.get("subject") == subject and record.get("relation") == relation and record.get("object") in expected_values:
            matched_records.append({
                "index": index,
                "subject": record.get("subject"),
                "relation": record.get("relation"),
                "object": record.get("object"),
            })
            before_keys = sorted(record.keys())
            record.update(annotation)
            if updated_records[index] != original_records[index]:
                changed_records.append({
                    "index": index,
                    "before_keys": before_keys,
                    "after_keys": sorted(record.keys()),
                })

    if not matched_records:
        errors.append(f"{item.get('patch_id')}: no matching records found for metadata-only change")
    if formal_values_differ(original_records, updated_records):
        errors.append(f"{item.get('patch_id')}: metadata-only change attempted to alter formal values")

    return updated_records, {
        "review_id": item.get("review_id"),
        "patch_id": item.get("patch_id"),
        "change_type": "metadata_only",
        "target_file": target_file_for_item(item),
        "matched_records": matched_records,
        "changed_records": changed_records,
        "status": "ready" if not errors else "error",
    }, errors


def prepare_value_change(
    item: Dict[str, Any],
    decision: Dict[str, Any],
    records: List[Dict[str, Any]],
    allow_value_change: bool,
    apply_requested: bool,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
    errors: List[str] = []
    updated_records = deepcopy(records)
    expected_values = set(values_for_zh_source(item))
    proposed_value = item.get("proposed_value")
    subject = item.get("subject")
    relation = item.get("relation")
    blocked = not allow_value_change
    matched_records = []
    changed_records = []

    if blocked:
        if apply_requested:
            errors.append(f"{item.get('patch_id')}: value_change requires --allow-value-change")
        return updated_records, {
            "review_id": item.get("review_id"),
            "patch_id": item.get("patch_id"),
            "change_type": "value_change",
            "risk_level": item.get("risk_level"),
            "target_file": target_file_for_item(item),
            "current_value": item.get("current_value"),
            "proposed_value": proposed_value,
            "status": "blocked_value_change" if apply_requested else "plan_only_high_risk",
            "blocked_by_default": True,
        }, errors

    if proposed_value is None:
        errors.append(f"{item.get('patch_id')}: value_change requires proposed_value")
    if not expected_values:
        errors.append(f"{item.get('patch_id')}: value_change requires current zh_wikipedia value evidence")

    for index, record in enumerate(updated_records):
        if not isinstance(record, dict):
            continue
        if record.get("subject") == subject and record.get("relation") == relation and record.get("object") in expected_values:
            matched_records.append({
                "index": index,
                "subject": record.get("subject"),
                "relation": record.get("relation"),
                "object": record.get("object"),
            })
            before = deepcopy(record)
            record["object"] = proposed_value
            record["quality_patch_id"] = item.get("patch_id")
            record["quality_review_id"] = item.get("review_id")
            record["quality_annotation"] = {
                "classification": item.get("issue_type"),
                "rationale": decision.get("human_reason") or item.get("system_recommendation", ""),
                "formal_value_changed": True,
                "reviewed_decision_source": "quality_review_decisions.json",
            }
            if record != before:
                changed_records.append({
                    "index": index,
                    "before": {key: before.get(key) for key in ("subject", "relation", "object")},
                    "after": {key: record.get(key) for key in ("subject", "relation", "object")},
                })

    if not matched_records:
        errors.append(f"{item.get('patch_id')}: no matching records found for value_change")

    return updated_records, {
        "review_id": item.get("review_id"),
        "patch_id": item.get("patch_id"),
        "change_type": "value_change",
        "risk_level": item.get("risk_level"),
        "target_file": target_file_for_item(item),
        "current_value": item.get("current_value"),
        "proposed_value": proposed_value,
        "matched_records": matched_records,
        "changed_records": changed_records,
        "status": "ready" if not errors else "error",
        "blocked_by_default": False,
    }, errors


def make_backup_dir(backup_root: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(backup_root, timestamp)
    candidate = base
    suffix = 2
    while os.path.exists(candidate):
        candidate = f"{base}_{suffix}"
        suffix += 1
    os.makedirs(candidate, exist_ok=False)
    return candidate


def create_rollback_manifest(backup_dir: str, target_files: Dict[str, List[str]]) -> Dict[str, Any]:
    entries = []
    for target_file, patch_ids in sorted(target_files.items()):
        source_path = os.path.abspath(target_file)
        backup_name = os.path.basename(source_path)
        backup_path = os.path.join(backup_dir, backup_name)
        counter = 2
        while os.path.exists(backup_path):
            stem, ext = os.path.splitext(backup_name)
            backup_path = os.path.join(backup_dir, f"{stem}_{counter}{ext}")
            counter += 1
        shutil.copy2(source_path, backup_path)
        entries.append({
            "original_path": source_path,
            "backup_path": os.path.abspath(backup_path),
            "original_sha256": file_sha256(source_path),
            "patch_ids": sorted(set(patch_ids)),
            "restore_instruction": "Copy backup_path back to original_path to roll back this file.",
        })
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backup_dir": os.path.abspath(backup_dir),
        "entries": entries,
        "chroma_written": False,
        "neo4j_written": False,
    }
    manifest_path = os.path.join(backup_dir, "rollback_manifest.json")
    dump_json(manifest_path, manifest)
    manifest["path"] = os.path.abspath(manifest_path)
    return manifest


def apply_quality_patch(
    *,
    decisions_path: str = DEFAULT_DECISIONS,
    candidates_path: str = DEFAULT_CANDIDATES,
    report_path: str = DEFAULT_REPORT,
    apply: bool = False,
    allow_value_change: bool = False,
    backup_root: str = DEFAULT_BACKUP_ROOT,
) -> Dict[str, Any]:
    dry_run = not apply
    decisions_payload = load_json(decisions_path)
    review_items, legacy_mode = load_review_items(candidates_path)
    item_by_patch = {item.get("patch_id"): item for item in review_items if item.get("patch_id")}
    decisions = _decisions(decisions_payload)
    errors: List[str] = []
    apply_plan: List[Dict[str, Any]] = []
    skipped_items: List[Dict[str, Any]] = []
    matched_records: List[Dict[str, Any]] = []
    changed_records: List[Dict[str, Any]] = []
    changed_by_file: Dict[str, List[Dict[str, Any]]] = {}
    patch_ids_by_file: Dict[str, List[str]] = {}
    records_by_file: Dict[str, List[Dict[str, Any]]] = {}
    value_change_files = set()
    formal_values_changed = False
    approved_count = 0

    for decision in decisions:
        patch_id = decision.get("patch_id")
        human_decision = decision.get("human_decision")
        item = item_by_patch.get(patch_id)
        if human_decision in NON_APPLY_DECISIONS:
            skipped_items.append({"patch_id": patch_id, "human_decision": human_decision})
            continue
        if human_decision != APPROVED_DECISION:
            skipped_items.append({"patch_id": patch_id, "human_decision": human_decision or "missing"})
            continue
        approved_count += 1
        if not item:
            errors.append(f"{patch_id}: approved decision has no review item")
            continue
        if not legacy_mode and not str(decision.get("human_reason", "")).strip():
            errors.append(f"{patch_id}: approved decision requires human_reason")
            continue
        if decision.get("safe_to_apply") is not True:
            errors.append(f"{patch_id}: approved decision must set safe_to_apply=true")
            continue
        if decision.get("approved_action") and decision.get("approved_action") != item.get("action"):
            errors.append(f"{patch_id}: approved_action does not match review action")
            continue

        change_type = item.get("change_type")
        if change_type == "metadata_only" or item.get("action") == "add_measurement_kind":
            target_file = target_file_for_item(item)
            if target_file not in records_by_file:
                records_by_file[target_file] = load_json(target_file)
                if not isinstance(records_by_file[target_file], list):
                    errors.append(f"{patch_id}: target file is not a list of triples")
                    continue
            updated_records, plan_item, item_errors = prepare_metadata_change(item, decision, records_by_file[target_file])
            records_by_file[target_file] = updated_records
            changed_by_file.setdefault(target_file, []).extend(plan_item.get("changed_records", []))
            if plan_item.get("changed_records"):
                patch_ids_by_file.setdefault(target_file, []).append(patch_id)
            matched_records.extend(plan_item.get("matched_records", []))
            changed_records.extend(plan_item.get("changed_records", []))
            apply_plan.append(plan_item)
            errors.extend(item_errors)
            continue

        if change_type == "value_change":
            target_file = target_file_for_item(item)
            if target_file not in records_by_file:
                records_by_file[target_file] = load_json(target_file)
                if not isinstance(records_by_file[target_file], list):
                    errors.append(f"{patch_id}: target file is not a list of triples")
                    continue
            updated_records, plan_item, item_errors = prepare_value_change(
                item,
                decision,
                records_by_file[target_file],
                allow_value_change,
                apply,
            )
            records_by_file[target_file] = updated_records
            changed_by_file.setdefault(target_file, []).extend(plan_item.get("changed_records", []))
            if plan_item.get("changed_records"):
                patch_ids_by_file.setdefault(target_file, []).append(patch_id)
                value_change_files.add(target_file)
            matched_records.extend(plan_item.get("matched_records", []))
            changed_records.extend(plan_item.get("changed_records", []))
            apply_plan.append(plan_item)
            errors.extend(item_errors)
            continue

        skipped_items.append({
            "patch_id": patch_id,
            "human_decision": human_decision,
            "reason": "approved item is manual-review/no-action and has no supported write operation",
        })

    for target_file, records in records_by_file.items():
        before = load_json(target_file)
        values_changed = formal_values_differ(before, records)
        if values_changed:
            formal_values_changed = True
        if values_changed and target_file not in value_change_files:
            errors.append(f"{target_file}: formal values changed unexpectedly")
        if values_changed and target_file in value_change_files and not allow_value_change:
            errors.append(f"{target_file}: value_change requires --allow-value-change")

    patches_applied = 0
    applied_count = 0
    backup_dir = None
    rollback_manifest = None
    if apply and not errors:
        files_to_write = {target_file: patch_ids_by_file.get(target_file, []) for target_file in changed_by_file if changed_by_file.get(target_file)}
        if files_to_write:
            backup_dir = make_backup_dir(backup_root)
            rollback_manifest = create_rollback_manifest(backup_dir, files_to_write)
        for target_file, records in records_by_file.items():
            if changed_by_file.get(target_file):
                dump_json(target_file, records)
                patches_applied += 1
                for plan_item in apply_plan:
                    if plan_item.get("target_file") == target_file and plan_item.get("changed_records"):
                        plan_item["status"] = "applied"
                        applied_count += 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "apply": bool(apply),
        "apply_metadata_only": bool(apply and not allow_value_change),
        "allow_value_change": bool(allow_value_change),
        "backup_dir": backup_dir,
        "rollback_manifest": rollback_manifest,
        "decisions_path": decisions_path,
        "queue_path": candidates_path,
        "approved_count": approved_count,
        "applied_count": applied_count,
        "skipped_count": len(skipped_items),
        "apply_plan": apply_plan,
        "matched_records": matched_records,
        "changed_records": changed_records,
        "skipped_items": skipped_items,
        "formal_values_changed": formal_values_changed,
        "patches_applied": patches_applied,
        "formal_data_written": bool(apply and patches_applied),
        "chroma_written": False,
        "neo4j_written": False,
        "errors": errors,
    }
    dump_json(report_path, report)
    if errors:
        raise RuntimeError("; ".join(errors))
    return report


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Preview or apply approved quality review decisions. Defaults to dry-run.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only. This is the default.")
    mode.add_argument("--apply", action="store_true", help="Deprecated alias for --apply-metadata-only.")
    mode.add_argument("--apply-metadata-only", action="store_true", help="Write supported approved metadata-only changes with backup and rollback manifest.")
    parser.add_argument("--allow-value-change", action="store_true", help="Allow approved value changes. High-risk changes are blocked without this flag.")
    parser.add_argument("--decisions", default=DEFAULT_DECISIONS)
    parser.add_argument("--queue", default=DEFAULT_CANDIDATES)
    parser.add_argument("--candidates", default=None, help="Deprecated alias for --queue.")
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--backup-root", default=DEFAULT_BACKUP_ROOT)
    args = parser.parse_args()
    apply_requested = bool(args.apply or args.apply_metadata_only)
    report = apply_quality_patch(
        decisions_path=args.decisions,
        candidates_path=args.candidates or args.queue,
        report_path=args.report,
        apply=apply_requested,
        allow_value_change=args.allow_value_change,
        backup_root=args.backup_root,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

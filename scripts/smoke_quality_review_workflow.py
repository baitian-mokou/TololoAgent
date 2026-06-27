from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, BASE_DIR, SOURCE_REGISTRY
from scripts.apply_quality_patches import apply_quality_patch


DEFAULT_REPORT = Path(BASE_DIR) / "evaluation" / "quality_review_workflow_smoke_report.json"
FINAL_ACCEPTANCE_REPORT = Path(BASE_DIR) / "evaluation" / "final_acceptance_report.json"


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_temp_review_fixture(root: Path) -> Tuple[Path, Path, Path, Path]:
    target = root / "data" / "triples" / "quality_smoke_triples.json"
    write_json(
        target,
        [
            {"subject": "天王星", "relation": "HAS_RADIUS", "object": "4km"},
            {"subject": "天王星", "relation": "HAS_RADIUS", "object": "20km"},
            {"subject": "金星", "relation": "HAS_RADIUS", "object": "1.0km"},
        ],
    )
    queue = {
        "schema_version": "quality_review_queue_v1",
        "items": [
            review_item("pending_patch", "pending", "metadata_only", target, ["4km"]),
            review_item("deferred_patch", "deferred", "metadata_only", target, ["4km"]),
            review_item("rejected_patch", "rejected", "metadata_only", target, ["4km"]),
            review_item("metadata_patch", "approved", "metadata_only", target, ["4km", "20km"]),
            review_item("value_patch", "approved", "value_change", target, ["1.0km"]),
        ],
    }
    decisions = {
        "schema_version": "quality_review_decisions_v1",
        "decisions": [
            decision_item("pending_patch", "pending"),
            decision_item("deferred_patch", "deferred"),
            decision_item("rejected_patch", "rejected"),
            decision_item("metadata_patch", "approved", "add_measurement_kind", True),
            decision_item("value_patch", "approved", "replace_value", True),
        ],
    }
    queue_path = root / "quality_review_queue.json"
    decisions_path = root / "quality_review_decisions.json"
    preview_path = root / "quality_review_apply_preview.json"
    write_json(queue_path, queue)
    write_json(decisions_path, decisions)
    return target, queue_path, decisions_path, preview_path


def review_item(patch_id: str, decision: str, change_type: str, target: Path, values: List[str]) -> Dict[str, Any]:
    is_value = change_type == "value_change"
    return {
        "review_id": f"qr_{patch_id}",
        "patch_id": patch_id,
        "subject": "金星" if is_value else "天王星",
        "relation": "HAS_RADIUS",
        "current_value": values if len(values) > 1 else values[0],
        "proposed_value": "6051.8 km" if is_value else None,
        "proposed_metadata": {} if is_value else {"measurement_kind": "unspecified_radius", "quality_status": "approved_metadata_only"},
        "issue_type": "true_value_conflict" if is_value else "measurement_kind_mismatch",
        "risk_level": "high" if is_value else "low",
        "source_evidence": {"values_by_source": {"zh_wikipedia": values}},
        "system_recommendation": "dry-run only",
        "human_decision": decision,
        "safe_to_apply": not is_value,
        "change_type": change_type,
        "action": "replace_value" if is_value else "add_measurement_kind",
        "target_file": str(target),
        "target_record_hint": {"subject": "金星" if is_value else "天王星", "relation": "HAS_RADIUS", "object": values[0]},
    }


def decision_item(patch_id: str, human_decision: str, approved_action: str = None, safe_to_apply: bool = False) -> Dict[str, Any]:
    return {
        "review_id": f"qr_{patch_id}",
        "patch_id": patch_id,
        "human_decision": human_decision,
        "human_reason": "approved_in_smoke" if human_decision == "approved" else "",
        "approved_action": approved_action if human_decision == "approved" else None,
        "safe_to_apply": safe_to_apply if human_decision == "approved" else False,
    }


def check(name: str, passed: bool, **details: Any) -> Dict[str, Any]:
    payload = {"name": name, "passed": bool(passed)}
    payload.update(details)
    return payload


def run_smoke(final_report_path: Path = FINAL_ACCEPTANCE_REPORT, write_report: bool = True, output_path: Path = DEFAULT_REPORT) -> Tuple[Dict[str, Any], int]:
    checks: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        target, queue_path, decisions_path, preview_path = build_temp_review_fixture(Path(tmpdir))
        before = target.read_text(encoding="utf-8")
        dry_run_report = apply_quality_patch(
            decisions_path=str(decisions_path),
            candidates_path=str(queue_path),
            report_path=str(preview_path),
            apply=False,
            allow_value_change=False,
        )
        after_dry_run = target.read_text(encoding="utf-8")
        skipped = {item["patch_id"]: item for item in dry_run_report["skipped_items"]}
        plan_by_patch = {item["patch_id"]: item for item in dry_run_report["apply_plan"]}

        checks.append(check("pending_does_not_write", "pending_patch" in skipped and before == after_dry_run))
        checks.append(check("deferred_does_not_write", "deferred_patch" in skipped and before == after_dry_run))
        checks.append(check("rejected_does_not_write", "rejected_patch" in skipped and before == after_dry_run))
        checks.append(check("approved_metadata_only_dry_run_plan", plan_by_patch.get("metadata_patch", {}).get("change_type") == "metadata_only" and before == after_dry_run))
        checks.append(check("high_risk_value_change_blocked_by_default", plan_by_patch.get("value_patch", {}).get("status") == "plan_only_high_risk"))
        checks.append(check("dry_run_writes_no_chroma", dry_run_report.get("chroma_written") is False))
        checks.append(check("dry_run_writes_no_neo4j", dry_run_report.get("neo4j_written") is False))

        value_only_decisions = {
            "schema_version": "quality_review_decisions_v1",
            "decisions": [
                decision_item("value_patch", "approved", "replace_value", True),
            ],
        }
        write_json(decisions_path, value_only_decisions)
        apply_report = apply_quality_patch(
            decisions_path=str(decisions_path),
            candidates_path=str(queue_path),
            report_path=str(preview_path),
            apply=True,
            allow_value_change=False,
        )
        after_apply_attempt = target.read_text(encoding="utf-8")
        checks.append(check("high_risk_apply_attempt_writes_no_formal_value", before == after_apply_attempt and apply_report.get("patches_applied") == 0))
        checks.append(check("apply_attempt_writes_no_chroma", apply_report.get("chroma_written") is False))
        checks.append(check("apply_attempt_writes_no_neo4j", apply_report.get("neo4j_written") is False))

    registry_ok = (
        ACTIVE_SOURCE == "zh_wikipedia"
        and SOURCE_REGISTRY.get("zh_wikipedia") == "active"
        and all(SOURCE_REGISTRY.get(source) == "disabled" for source in ("wikidata", "nasa", "esa"))
    )
    checks.append(check("active_source_still_zh_wikipedia", registry_ok, active_source=ACTIVE_SOURCE))

    final_report = read_json(final_report_path) if final_report_path.exists() else {"passed": False, "missing": True}
    checks.append(check("run_all_gates_report_passed", final_report.get("passed") is True, final_report_path=str(final_report_path)))

    report = {
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "formal_triples_written": False,
        "chroma_written": False,
        "neo4j_written": False,
        "active_source": ACTIVE_SOURCE,
    }
    if write_report:
        write_json(output_path, report)
    return report, 0 if report["passed"] else 1


def main() -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Smoke-test the quality review workflow safety boundaries.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--final-report", default=str(FINAL_ACCEPTANCE_REPORT))
    args = parser.parse_args()
    report, exit_code = run_smoke(Path(args.final_report), write_report=True, output_path=Path(args.report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

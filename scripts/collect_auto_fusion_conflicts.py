from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import BASE_DIR


DEFAULT_OUTPUT = os.path.join(BASE_DIR, "data", "quality_patches", "auto_fusion_conflict_candidates.json")
DEFAULT_INPUT = os.path.join(BASE_DIR, "evaluation", "auto_source_router_report.json")
DEFAULT_REPORT = os.path.join(BASE_DIR, "evaluation", "ingestion", "auto_fusion_conflict_report.json")


def _normalize_values_by_source(values: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    values_by_source: Dict[str, List[str]] = {}
    for item in values:
        obj = str(item.get("object", "")).strip()
        for source_name in item.get("sources", []):
            values_by_source.setdefault(str(source_name).strip(), []).append(obj)
    return values_by_source


def _extract_conflicts(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return list(payload)
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("conflicts"), list):
        return list(payload.get("conflicts", []))

    conflicts: List[Dict[str, Any]] = []
    for case in payload.get("cases", []):
        for conflict in case.get("conflicts", []):
            normalized = dict(conflict)
            normalized.setdefault("query", case.get("query", ""))
            normalized.setdefault("selected_sources", case.get("selected_sources", []))
            normalized.setdefault("authority_source", case.get("authority_source", ""))
            conflicts.append(normalized)
    return conflicts


def _aggregate_fusion_summary(payload: Any) -> Dict[str, int]:
    summary = {
        "multi_source_agreement_count": 0,
        "near_equivalent_values_count": 0,
        "measurement_kind_difference_count": 0,
        "human_review_required_count": 0,
    }
    if not isinstance(payload, dict):
        return summary
    for case in payload.get("cases", []):
        case_summary = case.get("cross_source_fusion_summary", {}) or {}
        for key in summary:
            summary[key] += int(case_summary.get(key, 0) or 0)
    return summary


def build_auto_fusion_conflict_candidates(conflicts: List[Dict[str, Any]], output_path: str | None = None) -> Dict[str, Any]:
    candidates = []
    for index, conflict in enumerate(conflicts, start=1):
        subject = str(conflict.get("subject", "")).strip()
        relation = str(conflict.get("relation", "")).strip()
        authority_source = str(conflict.get("authority_source", "")).strip()
        query = str(conflict.get("query", "")).strip()
        values = list(conflict.get("values", []))
        candidates.append({
            "patch_id": f"auto_fusion_conflict_{index:03d}",
            "classification": "true_value_conflict",
            "action": "no_action_manual_review",
            "authority_source": authority_source,
            "target_source": authority_source or "auto_fusion",
            "target_file": "",
            "target_record_hint": {
                "subject": subject,
                "relation": relation,
                "object": str(values[0].get("object", "")).strip() if values else "",
            },
            "before": {
                "values_by_source": _normalize_values_by_source(values),
            },
            "after": {
                "proposal": "manual review; no automatic data change",
            },
            "rationale": f"Auto fusion detected conflicting peer-source facts for `{subject}` / `{relation}`.",
            "confidence": 0.8,
            "requires_human_approval": True,
            "query": query,
            "selected_sources": list(conflict.get("selected_sources", [])),
            "quality_review_origin": "auto_fusion",
        })

    payload = {
        "schema_version": "auto_fusion_conflict_candidates_v1",
        "summary": {
            "candidate_count": len(candidates),
        },
        "candidates": candidates,
    }
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def build_auto_fusion_conflict_report(
    conflicts: List[Dict[str, Any]],
    candidate_payload: Dict[str, Any],
    *,
    candidate_output_path: str = DEFAULT_OUTPUT,
    fusion_summary: Dict[str, int] | None = None,
    output_path: str | None = None,
) -> Dict[str, Any]:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "true_conflict_count": len(conflicts),
            "candidate_count": int(candidate_payload.get("summary", {}).get("candidate_count", 0)),
            **dict(fusion_summary or {}),
        },
        "conflicts": conflicts,
        "candidate_output": candidate_output_path,
    }
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Convert auto-fusion conflict packets into quality review candidates.")
    parser.add_argument("input", nargs="?", default=DEFAULT_INPUT, help="JSON file containing a list of conflict packets or a payload with `conflicts`.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    conflicts = _extract_conflicts(payload)
    fusion_summary = _aggregate_fusion_summary(payload)
    report = build_auto_fusion_conflict_candidates(list(conflicts or []), output_path=args.output)
    audit = build_auto_fusion_conflict_report(
        list(conflicts or []),
        report,
        candidate_output_path=args.output,
        fusion_summary=fusion_summary,
        output_path=args.report,
    )
    print(json.dumps({
        "input": args.input,
        "output": args.output,
        "report": args.report,
        "candidate_count": report["summary"]["candidate_count"],
        "true_conflict_count": audit["summary"]["true_conflict_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sandbox_manifest_candidates import SANDBOX_DIR, is_sandbox_path, write_json


DEFAULT_JSON = SANDBOX_DIR / "approved_small_batch_plan.json"
DEFAULT_MD = SANDBOX_DIR / "approved_small_batch_plan.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def candidate_snapshots(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(str(item.get("sandbox_report") or ""))
    if not path.exists():
        return []
    payload = read_json(path)
    snapshots = payload.get("selected_candidate_snapshots", [])
    return snapshots if isinstance(snapshots, list) else []


def plan_item(item: Dict[str, Any]) -> Dict[str, Any]:
    approved_size = int(item.get("approved_sample_size", 0) or 0)
    if approved_size <= 0:
        raise ValueError(f"{item.get('source_id')}: approved_sample_size must be positive")
    snapshots = candidate_snapshots(item)
    selected = snapshots[:approved_size]
    return {
        "source_id": item.get("source_id", ""),
        "approved_sample_size": approved_size,
        "candidate_count": int(item.get("candidate_count", 0) or 0),
        "selected_candidate_urls": [candidate.get("url", "") for candidate in selected],
        "selected_candidate_titles": [candidate.get("title", "") for candidate in selected],
        "quality_guard_required": True,
        "network_required_for_future_run": True,
        "execution_status": "not_run",
        "blocked_until": "manual command",
        "reviewer_notes": item.get("reviewer_notes", ""),
        "source_summary": {
            "accepted": int(item.get("accepted", 0) or 0),
            "review_needed": int(item.get("review_needed", 0) or 0),
            "exploratory": int(item.get("exploratory", 0) or 0),
            "rejected": int(item.get("rejected", 0) or 0),
        },
    }


def build_plan(summary: Dict[str, Any]) -> Dict[str, Any]:
    items = summary.get("items", [])
    if not isinstance(items, list):
        raise ValueError("review summary missing items list")
    plan_items = [
        plan_item(item)
        for item in items
        if isinstance(item, dict) and item.get("review_decision") == "approved_for_small_batch"
    ]
    return {
        "mode": "approved_small_batch_plan_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_summary_json": summary.get("generated_at", ""),
        "execution_status": "not_run",
        "network": False,
        "formal_pipeline_write": False,
        "summary": {
            "approved_sources": len(plan_items),
            "plan_items": len(plan_items),
        },
        "items": plan_items,
    }


def markdown(plan: Dict[str, Any]) -> str:
    lines = [
        "# Approved Small-Batch Plan Preview",
        "",
        "这是计划预览，不是执行结果；本报告不联网、不抓取、不写正式 data/raw_json、triples、Chroma 或 Neo4j。",
        "",
        "| source_id | approved_size | candidates | execution_status | blocked_until |",
        "|---|---:|---:|---|---|",
    ]
    for item in plan["items"]:
        lines.append(
            "| {source_id} | {approved_sample_size} | {candidate_count} | {execution_status} | {blocked_until} |".format(**item)
        )
    if not plan["items"]:
        lines.append("| _none_ | 0 | 0 | not_run | manual command |")
    lines.extend(["", "## Selected Candidates", ""])
    for item in plan["items"]:
        lines.extend([
            f"### {item['source_id']}",
            "",
            "| title | url |",
            "|---|---|",
        ])
        for title, url in zip(item["selected_candidate_titles"], item["selected_candidate_urls"]):
            lines.append(f"| {str(title).replace('|', '\\|')} | {str(url).replace('|', '\\|')} |")
        lines.append("")
    return "\n".join(lines)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Preview approved small-batch source plans without executing any collection.")
    parser.add_argument("--review-summary-json", required=True)
    parser.add_argument("--out-json", default=str(DEFAULT_JSON))
    parser.add_argument("--out-md", default=str(DEFAULT_MD))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    for path in (out_json, out_md):
        if not is_sandbox_path(path):
            print("outputs must stay under evaluation/source_quality/sandbox", file=sys.stderr)
            return 2
    try:
        plan = build_plan(read_json(Path(args.review_summary_json)))
    except ValueError as exc:
        print(f"plan validation failed: {exc}", file=sys.stderr)
        return 2
    write_json(out_json, plan)
    write_text(out_md, markdown(plan))
    print(f"approved_sources={plan['summary']['approved_sources']} plan_items={plan['summary']['plan_items']} execution_status=not_run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

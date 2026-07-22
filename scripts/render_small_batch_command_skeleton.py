from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sandbox_manifest_candidates import SANDBOX_DIR, is_sandbox_path, write_json


DEFAULT_JSON = SANDBOX_DIR / "small_batch_command_skeleton.json"
DEFAULT_MD = SANDBOX_DIR / "small_batch_command_skeleton.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def proposed_command(source_id: str, approved_size: int) -> str:
    return (
        "NOT EXECUTED / DRY RUN ONLY: "
        f"python scripts/preview_source_frontier.py --manifest configs/source_manifests/examples/{source_id}.json "
        f"--quality-score --limit {approved_size} --json-out evaluation/source_quality/sandbox/{source_id}_future_frontier_preview.json"
    )


def skeleton_item(item: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(item.get("source_id") or "")
    approved_size = int(item.get("approved_sample_size", 0) or 0)
    return {
        "source_id": source_id,
        "manual_approval_required": True,
        "execution_status": "not_run",
        "proposed_command": proposed_command(source_id, approved_size),
        "prerequisites": [
            "review approved_small_batch_plan preview",
            "confirm manifest validation passed",
            "confirm rejected samples were reviewed",
            "confirm ACTIVE_SOURCE remains zh_wikipedia",
        ],
        "checklist": [
            "operator manually approves this command",
            "run preview before any future ingest",
            "keep output under evaluation/source_quality/sandbox for this stage",
            "do not write data/raw_json, triples, Chroma, or Neo4j from this skeleton",
        ],
        "safety_guards": [
            "NOT EXECUTED",
            "DRY RUN",
            "manual approval required",
            "ACTIVE_SOURCE unchanged",
            "formal writes disabled",
            "network only after approval",
        ],
        "expected_outputs": [
            f"evaluation/source_quality/sandbox/{source_id}_future_frontier_preview.json",
            f"evaluation/source_quality/sandbox/{source_id}_future_quality_report.json",
        ],
        "approved_sample_size": approved_size,
        "candidate_count": int(item.get("candidate_count", 0) or 0),
    }


def build_skeleton(plan: Dict[str, Any]) -> Dict[str, Any]:
    items = [skeleton_item(item) for item in plan.get("items", []) if isinstance(item, dict)]
    return {
        "mode": "small_batch_command_skeleton",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution_status": "not_run",
        "network": False,
        "formal_pipeline_write": False,
        "summary": {"command_skeletons": len(items)},
        "items": items,
    }


def markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Small-Batch Command Skeleton",
        "",
        "NOT EXECUTED / DRY RUN: 这是人工执行前的操作包，不是执行结果；不联网、不抓取、不写正式库。",
        "",
        "闭环：自动筛查 -> 人审 -> 计划预览 -> 手动确认命令。",
        "",
        "| source_id | approved_size | execution_status | manual approval | proposed command |",
        "|---|---:|---|---|---|",
    ]
    for item in report["items"]:
        command = str(item["proposed_command"]).replace("|", "\\|")
        lines.append(
            f"| {item['source_id']} | {item['approved_sample_size']} | {item['execution_status']} | "
            f"{item['manual_approval_required']} | `{command}` |"
        )
    if not report["items"]:
        lines.append("| _none_ | 0 | not_run | true | `NOT EXECUTED / DRY RUN: no approved sources` |")
    lines.extend(["", "## Pre-Run Checklist", ""])
    for item in report["items"]:
        lines.append(f"### {item['source_id']}")
        for check in item["checklist"]:
            lines.append(f"- [ ] {check}")
        lines.append("")
    return "\n".join(lines)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Render NOT EXECUTED small-batch command skeletons from an approved plan preview.")
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--out-json", default=str(DEFAULT_JSON))
    parser.add_argument("--out-md", default=str(DEFAULT_MD))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    for path in (out_json, out_md):
        if not is_sandbox_path(path):
            print("outputs must stay under evaluation/source_quality/sandbox", file=sys.stderr)
            return 2
    report = build_skeleton(read_json(Path(args.plan_json)))
    write_json(out_json, report)
    write_text(out_md, markdown(report))
    print(f"command_skeletons={report['summary']['command_skeletons']} execution_status=not_run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

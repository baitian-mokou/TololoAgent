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


DEFAULT_JSON = SANDBOX_DIR / "network_probe_approval_package.json"
DEFAULT_MD = SANDBOX_DIR / "network_probe_approval_package.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def approval_item(item: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(item.get("source_id") or "")
    max_pages = int(item.get("max_pages", 0) or 0)
    command = str(item.get("proposed_command") or "")
    if "NOT EXECUTED" not in command:
        command = "NOT EXECUTED / REQUIRES EXPLICIT USER APPROVAL: " + command
    return {
        "source_id": source_id,
        "allowed_domains": item.get("allowed_domains", []),
        "seed_urls": item.get("seed_urls", []),
        "max_pages": max_pages,
        "rate_limit_seconds": float(item.get("rate_limit_seconds", 1.0) or 1.0),
        "quality_gate_required": bool(item.get("quality_gate_required", True)),
        "preview_only": bool(item.get("preview_only", True)),
        "approval_status": "pending_user_approval",
        "execution_status": "not_run",
        "network": False,
        "formal_pipeline_write": False,
        "preview_command": command,
        "checklist": [
            "confirm_domains match the intended candidate source",
            "confirm rate limit is acceptable before any future network preview",
            "confirm_output_path stays under evaluation/source_quality/sandbox",
            "confirm no formal write to data/raw_json, triples, Chroma, or Neo4j",
            "confirm_quality_gate remains enabled for preview-only results",
        ],
        "risks": [
            "future preview command would use network if manually run",
            "seed pages may link to off-topic pages even under allowed domains",
            "quality scoring still needs rejected-sample review after preview",
        ],
        "expected_report_paths": item.get("expected_outputs", []),
        "source_probe_status": item.get("probe_status", ""),
    }


def build_package(plan: Dict[str, Any]) -> Dict[str, Any]:
    items = [approval_item(item) for item in plan.get("items", []) if isinstance(item, dict)]
    return {
        "mode": "network_probe_approval_package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "approval_status": "pending_user_approval",
        "execution_status": "not_run",
        "network": False,
        "formal_pipeline_write": False,
        "summary": {
            "approval_items": len(items),
        },
        "items": items,
    }


def markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Network Probe Approval Package",
        "",
        "NOT EXECUTED / REQUIRES EXPLICIT USER APPROVAL. 本报告是 future preview-only 网络探测的人审材料，不是执行结果。",
        "",
        f"- approval_status: `{report['approval_status']}`",
        f"- execution_status: `{report['execution_status']}`",
        f"- network: `{report['network']}`",
        f"- formal_pipeline_write: `{report['formal_pipeline_write']}`",
        "",
    ]
    for item in report["items"]:
        lines.extend([
            f"## {item['source_id']}",
            "",
            "| field | value |",
            "|---|---|",
            f"| allowed_domains | `{', '.join(item.get('allowed_domains', []))}` |",
            f"| seed_urls | `{', '.join(item.get('seed_urls', []))}` |",
            f"| max_pages | `{item['max_pages']}` |",
            f"| rate_limit_seconds | `{item['rate_limit_seconds']}` |",
            f"| quality_gate_required | `{item['quality_gate_required']}` |",
            f"| preview_only | `{item['preview_only']}` |",
            f"| execution_status | `{item['execution_status']}` |",
            f"| network | `{item['network']}` |",
            f"| preview_command | `{str(item['preview_command']).replace('|', '\\|')}` |",
            "",
            "### Manual Checklist",
            "",
        ])
        for check in item["checklist"]:
            key = check.split()[0]
            lines.append(f"- [ ] {key}: {check}")
        lines.extend(["", "### Risks", ""])
        for risk in item["risks"]:
            lines.append(f"- {risk}")
        lines.append("")
    if not report["items"]:
        lines.append("_No approval items. Empty plan remains not_run._")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Render NOT EXECUTED approval package for preview-only network probes.")
    parser.add_argument("--probe-plan-json", required=True)
    parser.add_argument("--out-json", default=str(DEFAULT_JSON))
    parser.add_argument("--out-md", default=str(DEFAULT_MD))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    for path in (out_json, out_md):
        if not is_sandbox_path(path):
            print("outputs must stay under evaluation/source_quality/sandbox", file=sys.stderr)
            return 2
    report = build_package(read_json(Path(args.probe_plan_json)))
    write_json(out_json, report)
    write_text(out_md, markdown(report))
    print(f"approval_items={report['summary']['approval_items']} approval_status=pending_user_approval execution_status=not_run network=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

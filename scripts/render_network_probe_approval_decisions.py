from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sandbox_manifest_candidates import SANDBOX_DIR, is_sandbox_path, write_json


DEFAULT_JSON = SANDBOX_DIR / "network_probe_approval_decisions.json"
DEFAULT_MD = SANDBOX_DIR / "network_probe_approval_decisions.md"
VALID_DECISIONS = {"pending", "approved_for_preview_probe", "rejected", "needs_revision"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def decision_template(package: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "items": [
            {
                "source_id": item.get("source_id", ""),
                "approval_decision": "pending",
                "reviewer_notes": "",
                "approved_max_pages": 0,
            }
            for item in package.get("items", [])
            if isinstance(item, dict)
        ],
    }


def load_decisions(path: Path) -> Dict[str, Dict[str, Any]]:
    payload = read_json(path)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    decisions: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("approval decision item must be an object")
        source_id = str(item.get("source_id") or "").strip()
        decision = str(item.get("approval_decision") or "").strip()
        if decision not in VALID_DECISIONS:
            raise ValueError(f"invalid approval_decision for {source_id}: {decision}")
        decisions[source_id] = item
    return decisions


def apply_decision(item: Dict[str, Any], decision: Dict[str, Any] | None) -> Dict[str, Any]:
    source_id = str(item.get("source_id") or "")
    max_pages = int(item.get("max_pages", 0) or 0)
    value = "pending"
    notes = ""
    approved_pages = 0
    if decision:
        value = str(decision.get("approval_decision") or "pending").strip()
        notes = str(decision.get("reviewer_notes") or "")
        approved_pages = int(decision.get("approved_max_pages", 0) or 0)
    if approved_pages > max_pages:
        raise ValueError(f"{source_id}: approved_max_pages {approved_pages} exceeds max_pages {max_pages}")
    approval_status = {
        "pending": "pending_user_approval",
        "approved_for_preview_probe": "approved_for_manual_preview",
        "rejected": "rejected",
        "needs_revision": "needs_revision",
    }[value]
    next_action = {
        "pending": "wait for reviewer decision; do not run preview command",
        "approved_for_preview_probe": "manual operator may run preview-only command later; this report does not execute network",
        "rejected": "do not run preview command for this source",
        "needs_revision": "revise manifest/offline fixtures before approval",
    }[value]
    return {
        **item,
        "approval_decision": value,
        "approval_status": approval_status,
        "reviewer_notes": notes,
        "approved_max_pages": approved_pages,
        "execution_status": "not_run",
        "network": False,
        "formal_pipeline_write": False,
        "next_action": next_action,
    }


def build_report(package: Dict[str, Any], decisions: Dict[str, Dict[str, Any]] | None = None) -> Dict[str, Any]:
    decisions = decisions or {}
    package_items = [item for item in package.get("items", []) if isinstance(item, dict)]
    known_sources = {str(item.get("source_id") or "") for item in package_items}
    unknown = sorted(set(decisions) - known_sources)
    if unknown:
        raise ValueError(f"unknown source_id in approval decisions: {unknown}")
    items = [apply_decision(item, decisions.get(str(item.get("source_id") or ""))) for item in package_items]
    counts = Counter(item["approval_decision"] for item in items)
    top_status = "approved_for_manual_preview" if counts.get("approved_for_preview_probe") else "pending_user_approval"
    return {
        "mode": "network_probe_approval_decisions",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "approval_status": top_status,
        "execution_status": "not_run",
        "network": False,
        "formal_pipeline_write": False,
        "summary": {
            "items": len(items),
            "decision_counts": dict(sorted(counts.items())),
        },
        "items": items,
    }


def markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Network Probe Approval Decisions",
        "",
        "APPROVED DOES NOT EXECUTE NETWORK. 批准只表示未来可由人工手动运行 preview-only 命令；本报告仍是 not_run。",
        "",
        f"- approval_status: `{report['approval_status']}`",
        f"- execution_status: `{report['execution_status']}`",
        f"- network: `{report['network']}`",
        f"- formal_pipeline_write: `{report['formal_pipeline_write']}`",
        "",
        "| source_id | decision | status | approved_max_pages | execution_status | network | next_action |",
        "|---|---|---|---:|---|---|---|",
    ]
    for item in report["items"]:
        lines.append(
            "| {source_id} | {approval_decision} | {approval_status} | {approved_max_pages} | "
            "{execution_status} | {network} | {next_action} |".format(**item)
        )
    if not report["items"]:
        lines.append("| _none_ | pending | pending_user_approval | 0 | not_run | False | no approval items |")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Render filled approval decisions for NOT EXECUTED preview network probes.")
    parser.add_argument("--approval-package-json", required=True)
    parser.add_argument("--write-template", default="")
    parser.add_argument("--approval-decisions", default="")
    parser.add_argument("--out-json", default=str(DEFAULT_JSON))
    parser.add_argument("--out-md", default=str(DEFAULT_MD))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    template_path = Path(args.write_template) if args.write_template else None
    for path in (out_json, out_md, *([template_path] if template_path else [])):
        if not is_sandbox_path(path):
            print("outputs must stay under evaluation/source_quality/sandbox", file=sys.stderr)
            return 2
    package = read_json(Path(args.approval_package_json))
    try:
        decisions = load_decisions(Path(args.approval_decisions)) if args.approval_decisions else {}
        report = build_report(package, decisions)
    except ValueError as exc:
        print(f"approval decision validation failed: {exc}", file=sys.stderr)
        return 2
    write_json(out_json, report)
    write_text(out_md, markdown(report))
    if template_path:
        write_json(template_path, decision_template(package))
    print(f"approval_items={report['summary']['items']} decisions={report['summary']['decision_counts']} execution_status=not_run network=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

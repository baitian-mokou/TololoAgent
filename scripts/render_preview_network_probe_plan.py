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


DEFAULT_JSON = SANDBOX_DIR / "preview_network_probe_plan.json"
DEFAULT_MD = SANDBOX_DIR / "preview_network_probe_plan.md"
DEFAULT_MANIFEST_DIR = ROOT / "configs" / "source_manifests" / "candidates"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def manifest_for(source_id: str, manifest_dir: Path) -> Dict[str, Any]:
    path = Path(manifest_dir) / f"{source_id}.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def offline_quality_by_source(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return {
        str(item.get("source_id") or ""): item
        for item in items
        if isinstance(item, dict) and item.get("source_id")
    }


def probe_status(offline_item: Dict[str, Any] | None) -> tuple[str, list[str]]:
    if not offline_item:
        return "needs_quality_review", ["offline_quality_missing"]
    counts = offline_item.get("triage_counts", {}) if isinstance(offline_item.get("triage_counts"), dict) else {}
    sample_count = int(offline_item.get("sample_count", 0) or 0)
    good = sum(int(counts.get(name, 0) or 0) for name in ("accepted", "review_needed", "exploratory"))
    rejected = int(counts.get("rejected", 0) or 0)
    if sample_count > 0 and rejected == sample_count and good == 0:
        return "blocked", ["needs_quality_review", "offline_fixture_all_rejected"]
    return "planned", []


def proposed_command(source_id: str, max_pages: int) -> str:
    return (
        "NOT EXECUTED / PREVIEW ONLY: "
        f"python scripts/preview_source_frontier.py --manifest configs/source_manifests/candidates/{source_id}.json "
        f"--fetch-links --quality-score --limit {max_pages} "
        f"--json-out evaluation/source_quality/sandbox/{source_id}_preview_network_probe.json"
    )


def plan_item(item: Dict[str, Any], offline_items: Dict[str, Dict[str, Any]], manifest_dir: Path) -> Dict[str, Any] | None:
    source_id = str(item.get("source_id") or "")
    approved_size = int(item.get("approved_sample_size", 0) or 0)
    if not source_id or approved_size <= 0:
        return None
    manifest = manifest_for(source_id, manifest_dir)
    max_pages = min(approved_size, 10)
    status, block_reasons = probe_status(offline_items.get(source_id))
    return {
        "source_id": source_id,
        "approved_sample_size": approved_size,
        "max_pages": max_pages,
        "rate_limit_seconds": float(manifest.get("crawl_delay", 1.0) or 1.0),
        "allowed_domains": manifest.get("allowed_domains", []) if isinstance(manifest.get("allowed_domains"), list) else [],
        "seed_urls": manifest.get("seed_urls", []) if isinstance(manifest.get("seed_urls"), list) else [],
        "quality_gate_required": True,
        "preview_only": True,
        "execution_status": "not_run",
        "network": False,
        "formal_pipeline_write": False,
        "requires_explicit_user_approval": True,
        "probe_status": status,
        "block_reasons": block_reasons,
        "proposed_command": proposed_command(source_id, max_pages),
        "expected_outputs": [
            f"evaluation/source_quality/sandbox/{source_id}_preview_network_probe.json",
        ],
        "safety_guards": [
            "NOT EXECUTED",
            "PREVIEW ONLY",
            "requires explicit user approval",
            "max_pages <= 10",
            "network=false in this plan",
            "formal pipeline writes disabled",
        ],
        "offline_quality_summary": (offline_items.get(source_id) or {}).get("triage_counts", {}),
    }


def build_plan(approved_plan: Dict[str, Any], offline_quality: Dict[str, Any], manifest_dir: Path) -> Dict[str, Any]:
    offline_items = offline_quality_by_source(offline_quality)
    items = []
    for raw_item in approved_plan.get("items", []):
        if not isinstance(raw_item, dict):
            continue
        item = plan_item(raw_item, offline_items, manifest_dir)
        if item is not None:
            items.append(item)
    status_counts: Dict[str, int] = {}
    for item in items:
        status = str(item.get("probe_status") or "planned")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "mode": "preview_network_probe_plan",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution_status": "not_run",
        "network": False,
        "formal_pipeline_write": False,
        "summary": {
            "plan_items": len(items),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "items": items,
    }


def markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Preview Network Probe Plan",
        "",
        "NOT EXECUTED: 这是未来 preview-only 网络探测的安全预演，不是执行结果。本阶段不联网、不抓取、不写正式库。",
        "",
        "| source_id | max_pages | rate_limit_s | status | network | preview_only | approval | command |",
        "|---|---:|---:|---|---|---|---|---|",
    ]
    for item in report["items"]:
        command = str(item["proposed_command"]).replace("|", "\\|")
        lines.append(
            f"| {item['source_id']} | {item['max_pages']} | {item['rate_limit_seconds']} | "
            f"{item['probe_status']} | {item['network']} | {item['preview_only']} | "
            f"{item['requires_explicit_user_approval']} | `{command}` |"
        )
    if not report["items"]:
        lines.append("| _none_ | 0 | 0 | planned | False | True | True | `NOT EXECUTED: no approved sources` |")
    lines.extend([
        "",
        "## Safety",
        "",
        "- `execution_status=not_run`",
        "- `network=false` in this plan",
        "- `formal_pipeline_write=false`",
        "- future command requires explicit user approval",
        "- command is preview-only and writes only sandbox/evaluation reports",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Render a NOT EXECUTED preview-only network probe plan.")
    parser.add_argument("--approved-plan-json", required=True)
    parser.add_argument("--offline-quality-json", default="")
    parser.add_argument("--manifest-dir", default=str(DEFAULT_MANIFEST_DIR))
    parser.add_argument("--out-json", default=str(DEFAULT_JSON))
    parser.add_argument("--out-md", default=str(DEFAULT_MD))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    for path in (out_json, out_md):
        if not is_sandbox_path(path):
            print("outputs must stay under evaluation/source_quality/sandbox", file=sys.stderr)
            return 2
    approved_plan = read_json(Path(args.approved_plan_json))
    offline_quality = read_json(Path(args.offline_quality_json)) if args.offline_quality_json else {}
    report = build_plan(approved_plan, offline_quality, Path(args.manifest_dir))
    write_json(out_json, report)
    write_text(out_md, markdown(report))
    print(f"plan_items={report['summary']['plan_items']} status={report['summary']['status_counts']} execution_status=not_run network=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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


DEFAULT_JSON = SANDBOX_DIR / "manual_preview_command_card.json"
DEFAULT_MD = SANDBOX_DIR / "manual_preview_command_card.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def manual_command(item: Dict[str, Any]) -> str:
    source_id = str(item.get("source_id") or "")
    pages = int(item.get("approved_max_pages", 0) or 0)
    return (
        "NOT EXECUTED / MANUAL ONLY / PREVIEW ONLY: "
        f"python scripts/preview_source_frontier.py --manifest configs/source_manifests/candidates/{source_id}.json "
        f"--fetch-links --quality-score --limit {pages} "
        f"--json-out evaluation/source_quality/sandbox/{source_id}_manual_preview_probe.json"
    )


def command_card(item: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(item.get("source_id") or "")
    expected_outputs = [f"evaluation/source_quality/sandbox/{source_id}_manual_preview_probe.json"]
    return {
        "source_id": source_id,
        "approved_max_pages": int(item.get("approved_max_pages", 0) or 0),
        "allowed_domains": item.get("allowed_domains", []),
        "seed_urls": item.get("seed_urls", []),
        "rate_limit_seconds": float(item.get("rate_limit_seconds", 1.0) or 1.0),
        "manual_command": manual_command(item),
        "preflight_checklist": [
            "confirm ACTIVE_SOURCE remains zh_wikipedia",
            "confirm allowed domains and seed URLs are still intended",
            "confirm rate limit and approved page limit before manual execution",
            "confirm quality gate remains enabled",
            "confirm no formal write to data/raw_json, triples, Chroma, or Neo4j",
            "confirm output path stays under evaluation/source_quality/sandbox",
        ],
        "expected_outputs": expected_outputs,
        "execution_status": "not_run",
        "network": False,
        "formal_pipeline_write": False,
        "approval_status": item.get("approval_status", ""),
        "reviewer_notes": item.get("reviewer_notes", ""),
    }


def approved_items(report: Dict[str, Any], sources: Sequence[str]) -> list[Dict[str, Any]]:
    requested = set(sources)
    items = [
        item
        for item in report.get("items", [])
        if isinstance(item, dict)
        and item.get("approval_status") == "approved_for_manual_preview"
        and (not requested or item.get("source_id") in requested)
    ]
    if requested and not items:
        raise ValueError(f"requested source is not approved_for_manual_preview: {sorted(requested)}")
    return items


def build_cards(report: Dict[str, Any], sources: Sequence[str]) -> Dict[str, Any]:
    items = [command_card(item) for item in approved_items(report, sources)]
    return {
        "mode": "manual_preview_command_card",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution_status": "not_run",
        "network": False,
        "formal_pipeline_write": False,
        "summary": {"command_cards": len(items)},
        "items": items,
    }


def markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Manual Preview Command Card",
        "",
        "NOT EXECUTED / MANUAL ONLY / PREVIEW ONLY. 本卡片只供未来人工确认后手动执行 preview-only 探测。",
        "",
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
            f"| approved_max_pages | `{item['approved_max_pages']}` |",
            f"| allowed_domains | `{', '.join(item.get('allowed_domains', []))}` |",
            f"| seed_urls | `{', '.join(item.get('seed_urls', []))}` |",
            f"| rate_limit_seconds | `{item['rate_limit_seconds']}` |",
            f"| manual_command | `{str(item['manual_command']).replace('|', '\\|')}` |",
            "",
            "### Preflight Checklist",
            "",
        ])
        for check in item["preflight_checklist"]:
            lines.append(f"- [ ] {check}")
        lines.extend(["", "### Expected Outputs", ""])
        for path in item["expected_outputs"]:
            lines.append(f"- `{path}`")
        lines.append("")
    if not report["items"]:
        lines.append("_No approved manual preview command cards._")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Render NOT EXECUTED manual preview command cards.")
    parser.add_argument("--approval-decisions-json", required=True)
    parser.add_argument("--source", action="append", default=[])
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
        report = build_cards(read_json(Path(args.approval_decisions_json)), args.source)
    except ValueError as exc:
        print(f"manual command card validation failed: {exc}", file=sys.stderr)
        return 2
    write_json(out_json, report)
    write_text(out_md, markdown(report))
    print(f"command_cards={report['summary']['command_cards']} execution_status=not_run network=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.ingest_manifest_frontier import (
    default_frontier_path,
    fetch_url,
    ingest_frontier,
    load_manifest,
    read_json as read_required_json,
)


ALLOWED_SOURCES = ("nasa", "esa")
Fetcher = Callable[[str, int], Dict[str, str]]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def output_allowed(path: Path) -> bool:
    parts = list(path.resolve().parts)
    if "docs" in parts:
        return True
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1))


def raw_count(raw_root: Path, source: str) -> int:
    path = raw_root / source
    return len(list(path.glob("*.json"))) if path.exists() else 0


def safety_fields() -> Dict[str, bool]:
    return {
        "raw_only": True,
        "triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
    }


def dry_run_item(root: Path, raw_root: Path, source: str, limit: int) -> Dict[str, Any]:
    frontier = read_json(default_frontier_path(source))
    before = raw_count(raw_root, source)
    candidates = len(frontier.get("accepted", [])) if isinstance(frontier.get("accepted"), list) else 0
    return {
        "source_id": source,
        "status": "dry_run",
        "before_raw_count": before,
        "after_raw_count": before,
        "new_records": 0,
        "duplicate_skipped": 0,
        "failed": 0,
        "candidate_count": min(candidates, limit),
        "limit": limit,
        "network_attempted": False,
        "report_path": "",
        **safety_fields(),
    }


def run_source_trial(
    *,
    root: Path,
    raw_root: Path,
    report_dir: Path,
    source: str,
    limit: int,
    fetcher: Fetcher,
    dry_run: bool,
) -> Dict[str, Any]:
    if dry_run:
        return dry_run_item(root, raw_root, source, limit)

    before = raw_count(raw_root, source)
    report_path = report_dir / f"{source}_raw_shadow_batch_trial_phase39_ingestion_report.json"
    try:
        manifest = load_manifest(source)
        frontier = read_required_json(default_frontier_path(source))
        report = ingest_frontier(
            source_name=source,
            manifest=manifest,
            frontier=frontier,
            limit=limit,
            delay=0,
            raw_root=raw_root,
            report_path=report_path,
            fetcher=fetcher,
            quality_report=True,
            skip_rejected=False,
        )
        after = raw_count(raw_root, source)
        fetched = int(report.get("fetched_count") or 0)
        failed = int(report.get("failed_count") or 0)
        new_records = max(after - before, 0)
        return {
            "source_id": source,
            "status": "completed_with_failures" if failed else "completed",
            "before_raw_count": before,
            "after_raw_count": after,
            "new_records": new_records,
            "duplicate_skipped": max(fetched - new_records, 0),
            "failed": failed,
            "candidate_count": min(len(frontier.get("accepted", [])), limit)
            if isinstance(frontier.get("accepted"), list)
            else 0,
            "limit": limit,
            "network_attempted": True,
            "report_path": str(report_path.relative_to(root)) if report_path.is_relative_to(root) else str(report_path),
            "skipped": int(report.get("skipped_count") or 0),
            **safety_fields(),
        }
    except Exception as exc:
        after = raw_count(raw_root, source)
        return {
            "source_id": source,
            "status": "failed",
            "before_raw_count": before,
            "after_raw_count": after,
            "new_records": max(after - before, 0),
            "duplicate_skipped": 0,
            "failed": 1,
            "candidate_count": 0,
            "limit": limit,
            "network_attempted": True,
            "report_path": str(report_path),
            "error": f"{type(exc).__name__}: {exc}",
            **safety_fields(),
        }


def build_trial(
    *,
    root: Path = ROOT,
    sources: Sequence[str] = ALLOWED_SOURCES,
    limit: int = 20,
    raw_root: Path | None = None,
    report_dir: Path | None = None,
    fetcher: Fetcher = fetch_url,
    dry_run: bool = False,
) -> Dict[str, Any]:
    chosen = [source for source in sources if source in ALLOWED_SOURCES]
    skipped = [source for source in sources if source not in ALLOWED_SOURCES]
    raw_root = raw_root or root / "data" / "raw_json"
    report_dir = report_dir or root / "evaluation" / "four_source_expansion"
    items = [
        run_source_trial(
            root=root,
            raw_root=raw_root,
            report_dir=report_dir,
            source=source,
            limit=limit,
            fetcher=fetcher,
            dry_run=dry_run,
        )
        for source in chosen
    ]
    return {
        "phase": "Phase 39",
        "mode": "raw_only_shadow_batch_trial",
        "generated_at": utc_now(),
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "dry_run": dry_run,
        "skipped_sources": skipped,
        "summary": {
            "sources": len(items),
            "new_records": sum(int(item.get("new_records") or 0) for item in items),
            "duplicate_skipped": sum(int(item.get("duplicate_skipped") or 0) for item in items),
            "failed": sum(int(item.get("failed") or 0) for item in items),
        },
        "sources": items,
        "safety_boundaries": [
            "nasa/esa only",
            "raw JSON only",
            "no downstream materialization",
            "ACTIVE_SOURCE remains zh_wikipedia",
        ],
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# raw-only shadow ingest 小批次试跑",
        "",
        "本报告只覆盖 `nasa` / `esa`，不处理 `zh_wikipedia` 或 `wikidata`。",
        "",
        f"- phase: `{report['phase']}`",
        f"- active_source: `{report['active_source']}`",
        f"- dry_run: `{report['dry_run']}`",
        "",
        "| source | status | before raw | after raw | new | duplicate/existing | failed | network |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["sources"]:
        lines.append(
            f"| {item['source_id']} | `{item['status']}` | {item['before_raw_count']} | "
            f"{item['after_raw_count']} | {item['new_records']} | {item['duplicate_skipped']} | "
            f"{item['failed']} | `{item['network_attempted']}` |"
        )
    lines.extend(["", "## 安全边界", ""])
    for boundary in report["safety_boundaries"]:
        lines.append(f"- {boundary}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run nasa/esa raw-only shadow batch trial.")
    parser.add_argument("--sources", nargs="*", default=list(ALLOWED_SOURCES))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "raw_shadow_batch_trial_phase39.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "raw_shadow_batch_trial_phase39.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    if args.limit <= 0 or args.limit > 20:
        print("limit must be 1..20 for Phase 39", file=sys.stderr)
        return 2

    report = build_trial(sources=args.sources, limit=args.limit, dry_run=args.dry_run)
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    print(
        f"sources={report['summary']['sources']} new={report['summary']['new_records']} "
        f"duplicates={report['summary']['duplicate_skipped']} failed={report['summary']['failed']} "
        f"active_source={ACTIVE_SOURCE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

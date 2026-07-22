from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.ingest_manifest_frontier import (
    fetch_url,
    load_manifest,
    payload_for_record,
    raw_path_for,
    write_json,
)
from scripts.select_deduped_frontier_candidates import canonical_url, normalized_title, raw_fingerprints


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


def write_report_json(path: Path, payload: Any) -> None:
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


def parse_source_limits(values: Sequence[str]) -> Dict[str, int]:
    limits: Dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"source-limit must be source=limit: {value}")
        source, raw_limit = value.split("=", 1)
        limits[source.strip()] = int(raw_limit)
    return limits


def selected_by_source(selected: Dict[str, Any]) -> tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    result: Dict[str, List[Dict[str, Any]]] = {}
    skipped: List[str] = []
    for item in selected.get("sources", []) if isinstance(selected.get("sources"), list) else []:
        source = str(item.get("source_id") or "").strip()
        if source not in ALLOWED_SOURCES:
            if source:
                skipped.append(source)
            continue
        candidates = item.get("selected_candidates", [])
        result[source] = candidates if isinstance(candidates, list) else []
    return result, skipped


def raw_count(raw_root: Path, source: str) -> int:
    path = raw_root / source
    return len(list(path.glob("*.json"))) if path.exists() else 0


def record_for_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "url",
        "url": str(candidate.get("url") or "").strip(),
        "depth": int(candidate.get("depth", 0) or 0),
        "reason": candidate.get("source_reason") or candidate.get("reason") or "phase40_selected",
    }


def duplicate_candidate(candidate: Dict[str, Any], existing_urls: set[str], existing_titles: set[str]) -> bool:
    url_key = canonical_url(str(candidate.get("url") or ""))
    title_key = normalized_title(str(candidate.get("title") or ""))
    if url_key and url_key in existing_urls:
        return True
    if title_key and title_key in existing_titles:
        return True
    return False


def safety_fields() -> Dict[str, bool]:
    return {
        "network_attempted": True,
        "raw_only": True,
        "triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
    }


def run_source(
    *,
    source: str,
    candidates: Sequence[Dict[str, Any]],
    limit: int,
    raw_root: Path,
    fetcher: Fetcher,
) -> Dict[str, Any]:
    before = raw_count(raw_root, source)
    _raw_files, existing_urls, existing_titles = raw_fingerprints(raw_root / source)
    selected = list(candidates)[:limit]
    new_records = duplicate_skipped = failed = 0
    failed_urls: List[str] = []
    items: List[Dict[str, Any]] = []
    load_manifest(source)

    for candidate in selected:
        url = str(candidate.get("url") or "").strip()
        if duplicate_candidate(candidate, existing_urls, existing_titles):
            duplicate_skipped += 1
            items.append({"url": url, "title": candidate.get("title", ""), "status": "duplicate_skipped"})
            continue
        try:
            payload = payload_for_record(source, record_for_candidate(candidate), fetcher)
            output = raw_path_for(raw_root, source, payload)
            write_json(output, payload)
            new_records += 1
            if canonical_url(url):
                existing_urls.add(canonical_url(url))
            title = normalized_title(str(payload.get("title") or candidate.get("title") or ""))
            if title:
                existing_titles.add(title)
            items.append({"url": url, "title": payload.get("title", ""), "status": "written", "saved_path": str(output)})
        except Exception as exc:
            failed += 1
            failed_urls.append(url)
            items.append({"url": url, "title": candidate.get("title", ""), "status": "failed", "reason": type(exc).__name__})

    after = raw_count(raw_root, source)
    return {
        "source_id": source,
        "selected_requested": len(candidates),
        "attempted": len(selected),
        "before_raw_count": before,
        "after_raw_count": after,
        "new_records": max(after - before, new_records),
        "duplicate_skipped": duplicate_skipped,
        "failed": failed,
        "failed_urls": failed_urls,
        "limit": limit,
        "items": items,
        **safety_fields(),
    }


def build_report(
    *,
    selected_json: Path,
    source_limits: Dict[str, int],
    root: Path = ROOT,
    raw_root: Path | None = None,
    report_dir: Path | None = None,
    fetcher: Fetcher = fetch_url,
) -> Dict[str, Any]:
    selected = read_json(selected_json)
    by_source, skipped = selected_by_source(selected)
    raw_root = raw_root or root / "data" / "raw_json"
    report_dir = report_dir or root / "evaluation" / "four_source_expansion"
    sources: List[Dict[str, Any]] = []
    for source in ALLOWED_SOURCES:
        if source not in by_source:
            continue
        limit = int(source_limits.get(source, len(by_source[source])) or 0)
        if limit <= 0:
            continue
        sources.append(run_source(source=source, candidates=by_source[source], limit=limit, raw_root=raw_root, fetcher=fetcher))

    report = {
        "phase": "Phase 41",
        "mode": "selected_raw_only_shadow_ingest",
        "generated_at": utc_now(),
        "selected_json": str(selected_json),
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "skipped_sources": skipped,
        "summary": {
            "sources": len(sources),
            "new_records": sum(int(item["new_records"]) for item in sources),
            "duplicate_skipped": sum(int(item["duplicate_skipped"]) for item in sources),
            "failed": sum(int(item["failed"]) for item in sources),
        },
        "sources": sources,
        "safety_boundaries": [
            "only Phase 40 selected candidates",
            "nasa/esa only",
            "raw JSON only",
            "no downstream materialization",
            "ACTIVE_SOURCE remains zh_wikipedia",
        ],
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    return report


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# selected raw-only shadow ingest",
        "",
        "本报告只使用 Phase 40 去重候选，不重新发现 frontier，不写 triples/narratives/Chroma/Neo4j。",
        "",
        f"- phase: `{report['phase']}`",
        f"- active_source: `{report['active_source']}`",
        "",
        "| source | requested | attempted | before raw | after raw | new | duplicate | failed |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["sources"]:
        lines.append(
            f"| {item['source_id']} | {item['selected_requested']} | {item['attempted']} | "
            f"{item['before_raw_count']} | {item['after_raw_count']} | {item['new_records']} | "
            f"{item['duplicate_skipped']} | {item['failed']} |"
        )
    lines.extend(["", "## Failed URLs", ""])
    for item in report["sources"]:
        if item["failed_urls"]:
            lines.append(f"- `{item['source_id']}`: " + ", ".join(f"`{url}`" for url in item["failed_urls"]))
    lines.extend(["", "## 安全边界", ""])
    for boundary in report["safety_boundaries"]:
        lines.append(f"- {boundary}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Ingest Phase 40 selected nasa/esa candidates as raw JSON only.")
    parser.add_argument("--selected-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "deduped_frontier_candidates_phase40.json"))
    parser.add_argument("--source-limit", action="append", default=[])
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "selected_raw_shadow_ingest_phase41.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "selected_raw_shadow_ingest_phase41.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    try:
        limits = parse_source_limits(args.source_limit) if args.source_limit else {"nasa": 20, "esa": 8}
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    bad_sources = [source for source in limits if source not in ALLOWED_SOURCES]
    if bad_sources:
        print(f"only nasa/esa are allowed: {bad_sources}", file=sys.stderr)
        return 2

    report = build_report(selected_json=Path(args.selected_json), source_limits=limits)
    write_report_json(out_json, report)
    write_text(out_md, render_markdown(report))
    print(
        f"sources={report['summary']['sources']} new={report['summary']['new_records']} "
        f"duplicates={report['summary']['duplicate_skipped']} failed={report['summary']['failed']} "
        f"active_source={ACTIVE_SOURCE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SOURCES = ("nasa", "esa")


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


def canonical_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.split("#", 1)[0].split("?", 1)[0].strip()
    match = re.match(r"^(?P<scheme>https?://)?(?P<rest>.+)$", text, flags=re.I)
    rest = match.group("rest") if match else text
    rest = rest.strip().rstrip("/")
    if "/" in rest:
        host, path = rest.split("/", 1)
        path = "/" + re.sub(r"/+", "/", path)
    else:
        host, path = rest, ""
    return f"{host.lower()}{path.lower()}"


def normalized_title(value: str) -> str:
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", " ", str(value or "").strip().lower())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def url_like(value: Any) -> bool:
    return str(value or "").strip().lower().startswith(("http://", "https://"))


def raw_fingerprints(raw_dir: Path) -> tuple[int, set[str], set[str]]:
    url_keys: set[str] = set()
    title_keys: set[str] = set()
    files = list(raw_dir.glob("*.json")) if raw_dir.exists() else []
    for path in files:
        payload = read_json(path)
        for key in ("source_url", "url", "source_record_id"):
            value = payload.get(key)
            if url_like(value):
                url_keys.add(canonical_url(str(value)))
        for url in payload.get("visited_urls", []) if isinstance(payload.get("visited_urls"), list) else []:
            if url_like(url):
                url_keys.add(canonical_url(str(url)))
        title = normalized_title(str(payload.get("title") or ""))
        if title:
            title_keys.add(title)
    return len(files), url_keys, title_keys


def failed_url_keys(root: Path, source: str) -> set[str]:
    path = root / "evaluation" / "four_source_expansion" / f"{source}_raw_shadow_batch_trial_phase39_ingestion_report.json"
    payload = read_json(path)
    keys: set[str] = set()
    for item in payload.get("items", []) if isinstance(payload.get("items"), list) else []:
        if item.get("status") == "failed" and url_like(item.get("url")):
            keys.add(canonical_url(str(item.get("url"))))
    return keys


def frontier_records(root: Path, source: str) -> List[Dict[str, Any]]:
    path = root / "evaluation" / "source_frontiers" / f"{source}_frontier.json"
    payload = read_json(path)
    accepted = payload.get("accepted", [])
    return accepted if isinstance(accepted, list) else []


def candidate_identity(record: Dict[str, Any]) -> tuple[str, str]:
    url = canonical_url(str(record.get("url") or ""))
    title = normalized_title(str(record.get("title") or record.get("entity") or record.get("qid") or ""))
    return url, title


def candidate_title(record: Dict[str, Any]) -> str:
    return str(record.get("title") or record.get("entity") or record.get("qid") or record.get("url") or "").strip()


def source_selection(root: Path, source: str, limit: int) -> Dict[str, Any]:
    raw_count, existing_urls, existing_titles = raw_fingerprints(root / "data" / "raw_json" / source)
    failed_urls = failed_url_keys(root, source)
    records = frontier_records(root, source)
    selected: List[Dict[str, Any]] = []
    duplicates = blocked = 0
    seen_selected_urls: set[str] = set()
    seen_selected_titles: set[str] = set()

    for record in records:
        url_key, title_key = candidate_identity(record)
        if url_key and url_key in failed_urls:
            blocked += 1
            continue
        duplicate = bool(url_key and url_key in existing_urls)
        if not url_key and title_key:
            duplicate = title_key in existing_titles
        if duplicate:
            duplicates += 1
            continue
        if (url_key and url_key in seen_selected_urls) or (not url_key and title_key in seen_selected_titles):
            duplicates += 1
            continue
        if url_key:
            seen_selected_urls.add(url_key)
        if title_key:
            seen_selected_titles.add(title_key)
        selected.append({
            "title": candidate_title(record),
            "url": str(record.get("url") or ""),
            "quality_triage": record.get("quality_triage"),
            "quality_score": record.get("quality_score"),
            "source_reason": record.get("reason", ""),
        })
        if len(selected) >= limit:
            break

    return {
        "source_id": source,
        "existing_raw_count": raw_count,
        "frontier_total": len(records),
        "duplicate_candidates": duplicates,
        "failed_or_blocked_candidates": blocked,
        "selected_count": len(selected),
        "selected_candidates": selected,
        "suggested_offset_or_skip_count": duplicates + blocked,
        "next_action": "ready_for_raw_shadow_trial" if selected else "needs_frontier_refresh",
    }


def build_report(
    *,
    root: Path = ROOT,
    sources: Sequence[str] = ALLOWED_SOURCES,
    limit: int = 50,
) -> Dict[str, Any]:
    chosen = [source for source in sources if source in ALLOWED_SOURCES]
    skipped = [source for source in sources if source not in ALLOWED_SOURCES]
    items = [source_selection(root, source, limit) for source in chosen]
    return {
        "phase": "Phase 40",
        "mode": "deduped_frontier_candidate_selection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources_requested": list(sources),
        "sources_skipped": skipped,
        "limit": limit,
        "summary": {
            "sources": len(items),
            "selected_total": sum(int(item["selected_count"]) for item in items),
            "duplicates_total": sum(int(item["duplicate_candidates"]) for item in items),
            "blocked_total": sum(int(item["failed_or_blocked_candidates"]) for item in items),
        },
        "sources": items,
        "safety_boundaries": [
            "selection report only",
            "no raw writes",
            "no downstream materialization",
            "nasa/esa remain shadow-only candidates",
        ],
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# 去重后的 frontier 扩批候选",
        "",
        "Phase 39 前 20 候选几乎全是重复记录；本报告先按已入库 raw URL/title 和失败 URL 做去重，选择下一批真正值得 raw-only trial 的候选。",
        "",
        f"- phase: `{report['phase']}`",
        f"- limit: `{report['limit']}`",
        "",
        "| source | existing raw | frontier total | duplicate | failed/blocked | selected | next action |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["sources"]:
        lines.append(
            f"| {item['source_id']} | {item['existing_raw_count']} | {item['frontier_total']} | "
            f"{item['duplicate_candidates']} | {item['failed_or_blocked_candidates']} | "
            f"{item['selected_count']} | `{item['next_action']}` |"
        )
    lines.extend(["", "## Selected Candidates", ""])
    for item in report["sources"]:
        lines.append(f"### {item['source_id']}")
        for candidate in item["selected_candidates"][:10]:
            title = candidate["title"] or candidate["url"]
            lines.append(f"- {title} - `{candidate['url']}`")
        if item["selected_count"] > 10:
            lines.append(f"- ... and {item['selected_count'] - 10} more")
        lines.append("")
    lines.extend(["## 安全边界", ""])
    for boundary in report["safety_boundaries"]:
        lines.append(f"- {boundary}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Select deduped nasa/esa frontier candidates for Phase 40.")
    parser.add_argument("--sources", nargs="*", default=list(ALLOWED_SOURCES))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "deduped_frontier_candidates_phase40.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "deduped_frontier_candidates_phase40.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    if args.limit <= 0:
        print("limit must be positive", file=sys.stderr)
        return 2

    report = build_report(sources=args.sources, limit=args.limit)
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    print(
        f"sources={report['summary']['sources']} selected={report['summary']['selected_total']} "
        f"duplicates={report['summary']['duplicates_total']} blocked={report['summary']['blocked_total']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

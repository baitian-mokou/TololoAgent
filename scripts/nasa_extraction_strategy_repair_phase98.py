from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.nasa_body_extraction_repair_phase96 import SCIENCE_TERMS, derive_title
from scripts.nasa_controlled_better_raw_preview_phase97 import fetch_url, html_to_text
from scripts.repair_four_source_review_package_phase94 import clean_nasa_text, is_nasa_navigation_residue


class MetaExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: List[str] = []
        self.json_ld: List[str] = []
        self._in_json_ld = False
        self._buf: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        values = {k.lower(): v or "" for k, v in attrs}
        if tag == "meta" and values.get("content") and values.get("name", values.get("property", "")).lower() in {
            "description",
            "og:description",
            "twitter:description",
        }:
            self.meta.append(values["content"])
        if tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._buf))
            self._in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._buf.append(data)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase98") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def quality_candidate(method: str, text: str) -> Dict[str, Any]:
    cleaned = clean_nasa_text(text)
    lower = cleaned.lower()
    words = re.findall(r"[A-Za-z]+", lower)
    science_hits = len(set(words) & SCIENCE_TERMS)
    listing_hits = sum(1 for phrase in ("featured", "highlights", "min read", "days ago", "article") if phrase in lower)
    accepted = bool(cleaned) and not is_nasa_navigation_residue(cleaned) and listing_hits < 3 and len(words) >= 10 and science_hits >= 2
    return {
        "method": method,
        "text": cleaned[:700],
        "text_length": len(cleaned),
        "boilerplate_score": round((listing_hits + (1 if is_nasa_navigation_residue(cleaned) else 0)) / 4, 2),
        "science_hits": science_hits,
        "accepted": accepted,
        "reject_reason": "" if accepted else "short_or_boilerplate_or_low_science_signal",
    }


def json_ld_texts(blob: str) -> List[tuple[str, str]]:
    try:
        data = json.loads(blob)
    except Exception:
        return []
    items = data if isinstance(data, list) else [data]
    out: List[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("articleBody", "description", "name"):
            value = item.get(key)
            if isinstance(value, str):
                out.append((f"json_ld_{key}", value))
    return out


def extraction_candidates(page: str) -> List[Dict[str, Any]]:
    parser = MetaExtractor()
    parser.feed(page)
    candidates = [quality_candidate("main_text", html_to_text(page))]
    candidates.extend(quality_candidate("meta_description", text) for text in parser.meta)
    for blob in parser.json_ld:
        candidates.extend(quality_candidate(method, text) for method, text in json_ld_texts(blob))
    return candidates


def phase97_urls(report: Dict[str, Any]) -> List[str]:
    urls = report.get("selected_urls", [])
    return [str(url) for url in urls] if isinstance(urls, list) else []


def best_candidate(candidates: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    accepted = [item for item in candidates if item["accepted"]]
    return max(accepted, key=lambda item: item["text_length"], default=None)


def build_report(*, urls: List[str], fetched: List[Dict[str, Any]], live_refetch_used: bool) -> Dict[str, Any]:
    rows = []
    for fetched_row in fetched:
        candidates = extraction_candidates(fetched_row.get("html", "")) if fetched_row.get("status") == "http_200" else []
        best = best_candidate(candidates)
        title = derive_title({"url": fetched_row["url"]}, best["text"] if best else fetched_row["url"])
        rows.append({
            "url": fetched_row["url"],
            "status": "accepted_reviewable" if best else ("failed" if fetched_row.get("status") == "failed" else "rejected_for_review"),
            "fetch_status": fetched_row.get("status"),
            "status_code": fetched_row.get("status_code"),
            "title": title,
            "extraction_candidates": candidates,
            "accepted_method": best["method"] if best else "",
            "body_excerpt": best["text"] if best else "",
            "reject_reason": "" if best else (fetched_row.get("failure_reason") or "no_strategy_extracted_reviewable_body"),
            "triples": [
                {"subject": title, "predicate": "SOURCE_URL", "object": fetched_row["url"]},
                {"subject": title, "predicate": "HAS_REVIEW_TEXT", "object": best["text"][:220]},
            ] if best else [],
            "quality_flags": ["phase98_strategy_preview", f"method:{best['method']}"] if best else ["phase98_no_reviewable_body"],
        })
    accepted = [row for row in rows if row["status"] == "accepted_reviewable"]
    failed = [row for row in rows if row["status"] == "failed"]
    return {
        "phase": "Phase 98",
        "mode": "nasa_extraction_strategy_repair_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_urls": urls,
        "attempted": len(fetched),
        "refetched": len(fetched) if live_refetch_used else 0,
        "accepted": len(accepted),
        "rejected": len(rows) - len(accepted) - len(failed),
        "failed": len(failed),
        "live_refetch_used": live_refetch_used,
        "per_url": rows,
        "method_breakdown": method_breakdown(rows),
        "quality_verdict": "nasa_extraction_strategy_found_reviewable_body" if accepted else "nasa_extraction_strategy_blocked_need_specific_endpoint",
        "production_ready": False,
        "apply_approved": False,
        "ingest_approved": False,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def method_breakdown(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        method = row.get("accepted_method") or "none"
        counts[method] = counts.get(method, 0) + 1
    return counts


def render_report(report: Dict[str, Any]) -> str:
    lines = [
        "# Phase98 NASA Extraction Strategy Repair Preview",
        "",
        f"- quality_verdict: `{report['quality_verdict']}`",
        f"- live_refetch_used: `{report['live_refetch_used']}`",
        f"- attempted: {report['attempted']}",
        f"- refetched: {report['refetched']}",
        f"- accepted: {report['accepted']}",
        f"- rejected: {report['rejected']}",
        f"- failed: {report['failed']}",
        f"- production_ready: `{report['production_ready']}`",
        "",
        "Per URL:",
    ]
    for row in report["per_url"]:
        lines.append(f"- `{row['status']}` `{row['title']}` {row['url']} method=`{row['accepted_method']}` reason=`{row['reject_reason']}`")
    lines.append("\nNext: use more specific NASA source endpoint/API/sitemap if accepted remains 0; no apply or ingest.")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Try NASA extraction strategies on Phase97 URL set only.")
    parser.add_argument("--phase97-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase97" / "nasa_controlled_better_raw_preview_phase97.json"))
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase98"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_extraction_strategy_repair_preview_phase98.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_md = Path(args.out_md)
    out_json = out_dir / "nasa_extraction_strategy_repair_preview_phase98.json"
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase98 or docs/", file=sys.stderr)
        return 2
    urls = phase97_urls(read_json(Path(args.phase97_report)))[:3]
    fetched = [fetch_url(url) for url in urls]
    report = build_report(urls=urls, fetched=fetched, live_refetch_used=bool(fetched))
    write_json(out_json, report)
    write_text(out_dir / "nasa_extraction_strategy_repair_preview_phase98.md", render_report(report))
    write_text(out_md, render_report(report))
    print(f"quality={report['quality_verdict']} attempted={report['attempted']} accepted={report['accepted']} rejected={report['rejected']} failed={report['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

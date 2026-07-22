from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.nasa_controlled_better_raw_preview_phase97 import fetch_url
from scripts.nasa_extraction_strategy_repair_phase98 import extraction_candidates


SPECIFIC_SEEDS = [
    "https://science.nasa.gov/mission/juno/",
    "https://science.nasa.gov/mission/cassini/",
    "https://science.nasa.gov/mission/voyager/",
    "https://science.nasa.gov/mission/new-horizons/",
    "https://science.nasa.gov/mission/mars-2020-perseverance/",
    "https://science.nasa.gov/solar-system/planets/mars/facts/",
    "https://science.nasa.gov/solar-system/planets/jupiter/facts/",
    "https://science.nasa.gov/solar-system/planets/saturn/facts/",
    "https://science.nasa.gov/solar-system/planets/uranus/facts/",
    "https://science.nasa.gov/solar-system/planets/neptune/facts/",
]
ALLOWED_HOSTS = {"science.nasa.gov", "www.nasa.gov", "nasa.gov", "nssdc.gsfc.nasa.gov", "solarsystem.nasa.gov"}
BAD_PARTS = ("/search", "/gallery", "/image", "/images", "/multimedia", "/tag/", "/category/")


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase99") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def is_specific_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in ALLOWED_HOSTS:
        return False
    if any(part in path for part in BAD_PARTS):
        return False
    return path.startswith("/mission/") or "/facts" in path or "/article/" in path


def select_specific_urls(urls: List[str], *, limit: int = 10) -> List[str]:
    selected: List[str] = []
    seen: set[str] = set()
    for url in urls:
        clean = str(url).strip()
        if clean.endswith("/") and clean[:-1] in seen:
            continue
        key = clean.rstrip("/")
        if is_specific_url(clean) and key not in seen:
            selected.append(clean)
            seen.add(key)
        if len(selected) >= limit:
            break
    return selected


def phase81_urls(path: Path) -> List[str]:
    phase81 = read_json(path)
    nasa = phase81.get("sources", {}).get("nasa", {}) if isinstance(phase81.get("sources"), dict) else {}
    rows = nasa.get("sample_candidates", []) if isinstance(nasa.get("sample_candidates"), list) else []
    return [str(row.get("url", "")) for row in rows]


def classify_page(page: str) -> Dict[str, Any]:
    candidates = extraction_candidates(page)
    accepted = [item for item in candidates if item.get("accepted")]
    if not accepted:
        thin = [
            item
            for item in candidates
            if item.get("method") in {"meta_description", "json_ld_description"}
            and item.get("text_length", 0) >= 45
            and item.get("science_hits", 0) >= 2
            and item.get("boilerplate_score", 1) < 0.5
        ]
        if thin:
            best_thin = max(thin, key=lambda item: item.get("text_length", 0))
            return {
                "status": "thin_evidence_review_candidate",
                "method": best_thin["method"],
                "text": best_thin["text"],
                "reason": "meta_or_description_only_thin_evidence",
            }
        return {"status": "rejected_for_review", "method": "", "text": "", "reason": "no_reviewable_body"}
    best = max(accepted, key=lambda item: item.get("text_length", 0))
    if best["method"] == "meta_description":
        return {"status": "thin_evidence_review_candidate", "method": best["method"], "text": best["text"], "reason": "meta_only_thin_evidence"}
    return {"status": "strong_accepted", "method": best["method"], "text": best["text"], "reason": ""}


def title_from_url(url: str) -> str:
    tail = urlparse(url).path.strip("/").split("/")[-1] or "NASA"
    return tail.replace("-", " ").title()


def build_report(*, urls: List[str], fetched: List[Dict[str, Any]], live_fetch_used: bool) -> Dict[str, Any]:
    previews = []
    for row in fetched:
        if row.get("status") != "http_200":
            classified = {"status": "failed", "method": "", "text": "", "reason": row.get("failure_reason", "fetch_failed")}
        else:
            classified = classify_page(row.get("html", ""))
        title = title_from_url(row["url"])
        text = classified.get("text", "")
        previews.append({
            "source": "nasa",
            "source_id": "nasa",
            "url": row["url"],
            "title": title,
            "fetch_status": row.get("status"),
            "status_code": row.get("status_code"),
            "review_status": classified["status"],
            "extraction_method": classified.get("method", ""),
            "body_excerpt": text,
            "reject_reason": classified.get("reason", ""),
            "quality_flags": ["specific_content_url", f"method:{classified.get('method', '')}"],
            "provenance": {"phase": "Phase99", "live_fetch_evaluation_only": live_fetch_used, "source_url": row["url"]},
            "triples": [
                {"subject": title, "predicate": "SOURCE_URL", "object": row["url"]},
                {"subject": title, "predicate": "HAS_REVIEW_TEXT", "object": text[:220]},
            ] if text else [],
        })
    strong = [row for row in previews if row["review_status"] == "strong_accepted"]
    thin = [row for row in previews if row["review_status"] == "thin_evidence_review_candidate"]
    failed = [row for row in previews if row["review_status"] == "failed"]
    rejected = [row for row in previews if row["review_status"] == "rejected_for_review"]
    return {
        "phase": "Phase 99",
        "mode": "nasa_specific_content_url_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "url_limit": 10,
        "selected_urls": urls,
        "attempted": len(fetched),
        "succeeded": sum(1 for row in fetched if row.get("status") == "http_200"),
        "strong_accepted": len(strong),
        "thin_accepted": len(thin),
        "rejected": len(rejected),
        "failed": len(failed),
        "live_fetch_used": live_fetch_used,
        "raw_previews": previews,
        "quality_verdict": "nasa_specific_content_strong_samples_found" if strong else "nasa_specific_content_needs_more_specific_sources",
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


def render_report(report: Dict[str, Any]) -> str:
    lines = [
        "# Phase99 NASA Specific Content URL Preview",
        "",
        f"- quality_verdict: `{report['quality_verdict']}`",
        f"- live_fetch_used: `{report['live_fetch_used']}`",
        f"- attempted: {report['attempted']}",
        f"- succeeded: {report['succeeded']}",
        f"- strong_accepted: {report['strong_accepted']}",
        f"- thin_accepted: {report['thin_accepted']}",
        f"- rejected: {report['rejected']}",
        f"- failed: {report['failed']}",
        f"- production_ready: `{report['production_ready']}`",
        "",
        "Per URL:",
    ]
    for row in report["raw_previews"]:
        lines.append(f"- `{row['review_status']}` `{row['title']}` {row['url']} method=`{row['extraction_method']}` reason=`{row['reject_reason']}`")
    lines.append("\nNext: review strong samples only; meta-only remains thin evidence. No apply or ingest.")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch NASA specific content URL preview under evaluation only.")
    parser.add_argument("--phase81-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase81" / "four_source_crawler_scope_expansion_phase81.json"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase99"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_specific_content_url_preview_phase99.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_md = Path(args.out_md)
    out_json = out_dir / "nasa_specific_content_url_preview_phase99.json"
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase99 or docs/", file=sys.stderr)
        return 2
    limit = min(max(args.limit, 1), 10)
    urls = select_specific_urls(SPECIFIC_SEEDS + phase81_urls(Path(args.phase81_report)), limit=limit)
    fetched = [fetch_url(url) for url in urls]
    report = build_report(urls=urls, fetched=fetched, live_fetch_used=bool(fetched))
    write_json(out_json, report)
    write_text(out_dir / "nasa_specific_content_url_preview_phase99.md", render_report(report))
    write_text(out_md, render_report(report))
    print(f"quality={report['quality_verdict']} attempted={report['attempted']} strong={report['strong_accepted']} thin={report['thin_accepted']} rejected={report['rejected']} failed={report['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

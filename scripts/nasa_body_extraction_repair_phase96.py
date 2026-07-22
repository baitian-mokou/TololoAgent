from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.repair_four_source_review_package_phase94 import clean_nasa_text, is_nasa_navigation_residue


NAV_PATH_HINTS = ("/search", "/gallery", "/image", "/images", "/multimedia", "/tag/")
SCIENCE_TERMS = {
    "mission",
    "planet",
    "spacecraft",
    "atmosphere",
    "asteroid",
    "comet",
    "moon",
    "jupiter",
    "mars",
    "solar",
    "science",
    "orbit",
    "studies",
}
LISTING_PHRASES = ("featured", "highlights", "min read", "days ago", "article")


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase96") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def derive_title(row: Dict[str, Any], text: str) -> str:
    title = str(row.get("title") or row.get("id") or "").strip()
    if title:
        return title
    first = re.split(r"\s+(?:Explore Search|News & Events|NASA Explore)\b", text, maxsplit=1)[0].strip(" -")
    if 3 <= len(first) <= 90:
        return first
    url_tail = str(row.get("url") or row.get("source_url") or "").rstrip("/").rsplit("/", 1)[-1]
    return url_tail.replace("-", " ").title()


def extract_body(row: Dict[str, Any]) -> str:
    text = str(row.get("text_excerpt") or row.get("content") or row.get("narrative_excerpt") or "")
    cleaned = clean_nasa_text(text)
    lower = cleaned.lower()
    if not cleaned or is_nasa_navigation_residue(cleaned):
        return ""
    if sum(1 for phrase in LISTING_PHRASES if phrase in lower) >= 3:
        return ""
    words = re.findall(r"[A-Za-z]+", cleaned.lower())
    if len(words) < 14 or len(set(words) & SCIENCE_TERMS) < 2:
        return ""
    return cleaned


def classify_row(row: Dict[str, Any]) -> Dict[str, Any]:
    url = str(row.get("url") or row.get("source_url") or "")
    text = str(row.get("text_excerpt") or row.get("content") or row.get("narrative_excerpt") or "")
    title = derive_title(row, text)
    if row.get("status") not in ("http_200", "succeeded", "success", None, ""):
        return {"status": "failed", "title": title, "url": url, "reason": row.get("failure_reason") or "raw_preview_failed"}
    if any(hint in url.lower() for hint in NAV_PATH_HINTS):
        return {"status": "rejected_search_or_nav", "title": title, "url": url, "reason": "url_path_search_gallery_or_media"}
    body = extract_body(row)
    if not body:
        return {
            "status": "rejected_search_or_nav",
            "title": title,
            "url": url,
            "reason": "no_non_navigation_body_in_existing_preview",
        }
    if not title or not url:
        return {"status": "rejected_boilerplate", "title": title, "url": url, "reason": "missing_title_or_url"}
    return {
        "status": "accepted_reviewable",
        "source": "nasa",
        "source_id": "nasa",
        "title": title,
        "url": url,
        "narrative": body,
        "triples": [
            {"subject": title, "predicate": "SOURCE_URL", "object": url},
            {"subject": title, "predicate": "HAS_REVIEW_TEXT", "object": body[:220]},
        ],
        "provenance": {
            "phase": "Phase96",
            "input_status": row.get("status"),
            "input_reason": row.get("reason"),
            "source_url": url,
        },
        "quality_flags": ["existing_evaluation_preview_only", "non_navigation_body_extracted"],
        "review_status": "pending_manual_or_reviewer_check",
    }


def build_preview(*, raw_previews: List[Dict[str, Any]]) -> Dict[str, Any]:
    nasa_rows = [row for row in raw_previews if row.get("source") == "nasa"]
    classified = [classify_row(row) for row in nasa_rows]
    accepted = [row for row in classified if row["status"] == "accepted_reviewable"]
    rejected_nav = [row for row in classified if row["status"] == "rejected_search_or_nav"]
    rejected_boilerplate = [row for row in classified if row["status"] == "rejected_boilerplate"]
    failed = [row for row in classified if row["status"] == "failed"]
    return {
        "phase": "Phase 96",
        "mode": "nasa_body_extraction_repair_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(nasa_rows),
        "accepted_reviewable": len(accepted),
        "rejected_boilerplate": len(rejected_boilerplate),
        "rejected_search_or_nav": len(rejected_nav),
        "failed": len(failed),
        "needs_live_refetch": len(accepted) == 0,
        "quality_verdict": "nasa_review_sample_repaired_preview"
        if accepted
        else "nasa_body_extraction_blocked_needs_better_raw",
        "reviewable_samples": accepted,
        "rejected_examples": (rejected_nav + rejected_boilerplate + failed)[:12],
        "root_cause": "Existing Phase82 NASA excerpts contain navigation/search/recent-news chrome before usable body text.",
        "production_ready": False,
        "apply_approved": False,
        "ingest_approved": False,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "live_fetch_used": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def build_preview_from_phase82(*, phase82_report: Path) -> Dict[str, Any]:
    phase82 = read_json(phase82_report)
    rows = phase82.get("raw_previews", []) if isinstance(phase82.get("raw_previews"), list) else []
    return build_preview(raw_previews=rows)


def render_report(report: Dict[str, Any]) -> str:
    lines = [
        "# Phase96 NASA Body Extraction Repair Preview",
        "",
        f"- quality_verdict: `{report['quality_verdict']}`",
        f"- production_ready: `{report['production_ready']}`",
        f"- live_fetch_used: `{report['live_fetch_used']}`",
        f"- candidate_count: {report['candidate_count']}",
        f"- accepted_reviewable: {report['accepted_reviewable']}",
        f"- rejected_search_or_nav: {report['rejected_search_or_nav']}",
        f"- rejected_boilerplate: {report['rejected_boilerplate']}",
        f"- failed: {report['failed']}",
        f"- needs_live_refetch: `{report['needs_live_refetch']}`",
        "",
        "Root cause: existing NASA evaluation previews are dominated by navigation/search/recent-news chrome.",
        "Next: re-sample NASA with better body extraction or provide richer existing raw; no shadow apply preflight yet.",
        "",
        "Rejected examples:",
    ]
    for row in report["rejected_examples"][:8]:
        lines.append(f"- `{row.get('status')}` `{row.get('title')}` {row.get('url')} - {row.get('reason')}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview NASA body extraction repair from evaluation-only raw previews.")
    parser.add_argument(
        "--phase82-report",
        default=str(ROOT / "evaluation" / "four_source_expansion" / "phase82" / "four_source_controlled_raw_preview_phase82.json"),
    )
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase96"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_body_extraction_repair_preview_phase96.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_md = Path(args.out_md)
    out_json = out_dir / "nasa_body_extraction_repair_preview_phase96.json"
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase96 or docs/", file=sys.stderr)
        return 2
    report = build_preview_from_phase82(phase82_report=Path(args.phase82_report))
    write_json(out_json, report)
    write_text(out_dir / "nasa_body_extraction_repair_preview_phase96.md", render_report(report))
    write_text(out_md, render_report(report))
    print(
        f"quality={report['quality_verdict']} accepted={report['accepted_reviewable']} "
        f"rejected_nav={report['rejected_search_or_nav']} failed={report['failed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

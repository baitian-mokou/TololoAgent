from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.nasa_body_extraction_repair_phase96 import SCIENCE_TERMS, derive_title
from scripts.repair_four_source_review_package_phase94 import clean_nasa_text, is_nasa_navigation_residue


ALLOWED_HOSTS = ("science.nasa.gov", "www.nasa.gov", "nasa.gov", "nssdc.gsfc.nasa.gov", "solarsystem.nasa.gov")
BAD_PATH_PARTS = ("/search", "/gallery", "/image", "/images", "/multimedia", "/tag/")
INDEX_PATHS = {
    "/solar-system",
    "/solar-system/",
    "/solar-system/planets",
    "/solar-system/planets/",
    "/solar-system/moons",
    "/solar-system/moons/",
    "/solar-system/dwarf-planets",
    "/solar-system/dwarf-planets/",
    "/solar-system/asteroids",
    "/solar-system/asteroids/",
    "/solar-system/comets",
    "/solar-system/comets/",
    "/mission",
    "/mission/",
    "/missions",
    "/missions/",
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip = 0
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer", "header", "aside"}:
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer", "header", "aside"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            text = data.strip()
            if text:
                self.parts.append(text)


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase97") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    specific_page = host == "nssdc.gsfc.nasa.gov" or path.startswith("/mission/")
    return (
        parsed.scheme in {"http", "https"}
        and host in ALLOWED_HOSTS
        and not any(part in path for part in BAD_PATH_PARTS)
        and path not in INDEX_PATHS
        and specific_page
    )


def select_candidates(rows: List[Dict[str, Any]], *, limit: int = 10) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        url = str(row.get("url") or row.get("source_url") or "")
        if row.get("source_id") != "nasa" or not allowed_url(url) or url in seen:
            continue
        seen.add(url)
        selected.append({"source_id": "nasa", "title": row.get("title", ""), "url": url, "reason": row.get("reason", "")})
        if len(selected) >= limit:
            break
    return selected


def html_to_text(page: str) -> str:
    parser = TextExtractor()
    parser.feed(page)
    return html.unescape(" ".join(parser.parts))


def extract_body(page: str) -> str:
    text = html_to_text(page)
    cleaned = clean_nasa_text(text)
    lower = cleaned.lower()
    listing_hits = sum(1 for phrase in ("featured", "highlights", "min read", "days ago", "article") if phrase in lower)
    words = re.findall(r"[A-Za-z]+", lower)
    if not cleaned or is_nasa_navigation_residue(cleaned) or listing_hits >= 3:
        return ""
    if len(words) < 12 or len(set(words) & SCIENCE_TERMS) < 2:
        return ""
    return cleaned[:700]


def fetch_url(url: str, *, timeout: int = 15) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "TololoAgent Phase97 evaluation-only preview"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(500_000)
            return {
                "url": url,
                "status": "http_200" if response.status == 200 else "http_non_200",
                "status_code": response.status,
                "html": raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        return {"url": url, "status": "failed", "status_code": exc.code, "failure_reason": str(exc)}
    except Exception as exc:
        return {"url": url, "status": "failed", "status_code": 0, "failure_reason": str(exc)}


def build_report(*, selected: List[Dict[str, Any]], fetched: List[Dict[str, Any]], live_fetch_used: bool) -> Dict[str, Any]:
    by_url = {row["url"]: row for row in selected}
    previews: List[Dict[str, Any]] = []
    for row in fetched:
        source = by_url.get(row["url"], {"title": "", "reason": ""})
        body = extract_body(row.get("html", "")) if row.get("status") == "http_200" else ""
        title = derive_title({"title": source.get("title"), "url": row["url"]}, body or row["url"])
        status = "accepted_reviewable" if body else ("failed" if row.get("status") == "failed" else "rejected_body_quality")
        previews.append({
            "source": "nasa",
            "source_id": "nasa",
            "url": row["url"],
            "title": title,
            "fetch_status": row.get("status"),
            "status_code": row.get("status_code"),
            "review_status": "pending_manual_or_reviewer_check" if body else "rejected_for_review",
            "body_excerpt": body,
            "quality_flags": ["live_fetch_evaluation_only", "non_navigation_body_extracted"] if body else ["no_reviewable_body_extracted"],
            "reject_reason": "" if body else (row.get("failure_reason") or "body_too_short_or_boilerplate"),
            "provenance": {"phase": "Phase97", "candidate_reason": source.get("reason"), "source_url": row["url"]},
            "triples": [
                {"subject": title, "predicate": "SOURCE_URL", "object": row["url"]},
                {"subject": title, "predicate": "HAS_REVIEW_TEXT", "object": body[:220]},
            ] if body else [],
        })
    accepted = [row for row in previews if row["review_status"] != "rejected_for_review"]
    failed = [row for row in previews if row["fetch_status"] == "failed"]
    rejected = [row for row in previews if row["review_status"] == "rejected_for_review" and row["fetch_status"] != "failed"]
    return {
        "phase": "Phase 97",
        "mode": "controlled_nasa_better_raw_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_limit": 10,
        "selected_urls": [row["url"] for row in selected],
        "attempted": len(fetched),
        "succeeded": sum(1 for row in fetched if row.get("status") == "http_200"),
        "accepted_reviewable": len(accepted),
        "rejected": len(rejected),
        "failed": len(failed),
        "raw_previews": previews,
        "live_fetch_used": live_fetch_used,
        "quality_verdict": "nasa_better_raw_reviewable_samples_found" if accepted else "nasa_better_raw_preview_still_blocked",
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


def phase81_nasa_candidates(path: Path) -> List[Dict[str, Any]]:
    phase81 = read_json(path)
    nasa = phase81.get("sources", {}).get("nasa", {}) if isinstance(phase81.get("sources"), dict) else {}
    return nasa.get("sample_candidates", []) if isinstance(nasa.get("sample_candidates"), list) else []


def render_report(report: Dict[str, Any]) -> str:
    lines = [
        "# Phase97 Controlled NASA Better-Raw Preview",
        "",
        f"- quality_verdict: `{report['quality_verdict']}`",
        f"- live_fetch_used: `{report['live_fetch_used']}`",
        f"- attempted: {report['attempted']}",
        f"- succeeded: {report['succeeded']}",
        f"- accepted_reviewable: {report['accepted_reviewable']}",
        f"- rejected: {report['rejected']}",
        f"- failed: {report['failed']}",
        f"- production_ready: `{report['production_ready']}`",
        "",
        "Selected URLs:",
    ]
    lines.extend(f"- {url}" for url in report["selected_urls"])
    lines.extend(["", "Preview outcomes:"])
    for row in report["raw_previews"]:
        lines.append(f"- `{row['review_status']}` `{row['title']}` {row['url']} - {row['reject_reason']}")
    lines.append("\nNext: review accepted samples if any; otherwise choose more specific NASA article/fact pages. No apply or ingest.")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controlled NASA better raw preview under evaluation only.")
    parser.add_argument("--phase81-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase81" / "four_source_crawler_scope_expansion_phase81.json"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase97"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_controlled_better_raw_preview_phase97.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    limit = min(max(args.limit, 1), 10)
    out_dir = Path(args.out_dir)
    out_md = Path(args.out_md)
    out_json = out_dir / "nasa_controlled_better_raw_preview_phase97.json"
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase97 or docs/", file=sys.stderr)
        return 2
    selected = select_candidates(phase81_nasa_candidates(Path(args.phase81_report)), limit=limit)
    fetched = [fetch_url(row["url"]) for row in selected]
    report = build_report(selected=selected, fetched=fetched, live_fetch_used=bool(fetched))
    write_json(out_json, report)
    write_text(out_dir / "nasa_controlled_better_raw_preview_phase97.md", render_report(report))
    write_text(out_md, render_report(report))
    print(
        f"quality={report['quality_verdict']} attempted={report['attempted']} "
        f"accepted={report['accepted_reviewable']} rejected={report['rejected']} failed={report['failed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

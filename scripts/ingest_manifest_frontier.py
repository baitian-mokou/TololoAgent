from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, Sequence
from urllib.parse import quote, urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.preview_source_frontier import (
    MANIFEST_DIR,
    domain_allowed,
    load_manifest,
    manifest_validation_report,
    normalize_url,
    path_contains,
    path_has_any,
    quality_context_from_manifest,
)
from src.source_quality.page_quality import score_page


RAW_ROOT = ROOT / "data" / "raw_json"
REPORT_DIR = ROOT / "evaluation" / "ingestion"
FRONTIER_DIR = ROOT / "evaluation" / "source_frontiers"
MIN_TEXT_LENGTH = 120
USER_AGENT = "tololo-manifest-ingest/1.0"
Fetcher = Callable[[str, int], Dict[str, str]]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: Sequence[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._in_title = True
        if lowered in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._in_title = False
        if lowered in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(str(data or "").split())
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        elif not self._skip_depth:
            self.text_parts.append(text)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", str(value or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._")
    return (cleaned or "record")[:120]


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def skip_reason_for_url(url: str, manifest: Dict[str, Any]) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return "unsupported_scheme"
    lower_path = parsed.path.lower()
    lower_url = url.lower()
    if any(lower_path.endswith(ext) for ext in (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".zip")):
        return "excluded_path"
    if any(part in lower_url for part in ("/search", "?search", "search=", "/tag/", "/tags/", "/privacy", "/terms", "/cookies")):
        return "excluded_path"
    if not domain_allowed(url, manifest.get("allowed_domains", [])):
        return "domain_not_allowed"
    if path_has_any(url, manifest.get("exclude_path_keywords", [])):
        return "excluded_path"
    if not path_contains(url, manifest.get("include_path_keywords", [])):
        return "missing_include_keyword"
    return ""


def fetch_url(url: str, timeout: int = 15) -> Dict[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        return {
            "url": response.geturl(),
            "content_type": str(response.headers.get("Content-Type") or ""),
            "body": body,
        }


def wikidata_entity_data_url(qid: str) -> str:
    return f"https://www.wikidata.org/wiki/Special:EntityData/{quote(qid)}.json"


def extract_html_payload(source_name: str, record: Dict[str, Any], fetched: Dict[str, str]) -> Dict[str, Any]:
    html = fetched.get("body", "")
    parser = TextExtractor()
    parser.feed(html)
    title = " ".join(parser.title_parts).strip() or record.get("entity") or record.get("url") or source_name
    text = " ".join(parser.text_parts).strip()
    return {
        "title": title,
        "source": source_name,
        "source_name": source_name,
        "source_record_id": record.get("qid") or record.get("url"),
        "source_url": record.get("url"),
        "url": fetched.get("url") or record.get("url"),
        "origin": "manifest_frontier",
        "html": html,
        "text": text,
        "text_length": len(text),
        "fetched_at": utc_now(),
        "discovery_depth": int(record.get("depth", 0) or 0),
    }


def extract_wikidata_payload(source_name: str, record: Dict[str, Any], fetched: Dict[str, str]) -> Dict[str, Any]:
    payload = json.loads(fetched.get("body") or "{}")
    qid = str(record.get("qid") or "").strip().upper()
    entity = payload.get("entities", {}).get(qid, {})
    labels = entity.get("labels", {})
    title = (
        labels.get("zh", {}).get("value")
        or labels.get("en", {}).get("value")
        or record.get("entity")
        or qid
    )
    text = json.dumps(entity.get("descriptions", {}), ensure_ascii=False)
    return {
        "title": title,
        "source": source_name,
        "source_name": source_name,
        "source_record_id": qid,
        "qid": qid,
        "source_url": record.get("url"),
        "url": fetched.get("url") or wikidata_entity_data_url(qid),
        "origin": "wikidata_entitydata",
        "entity": entity,
        "text": text,
        "text_length": len(text),
        "fetched_at": utc_now(),
        "discovery_depth": int(record.get("depth", 0) or 0),
    }


def payload_for_record(source_name: str, record: Dict[str, Any], fetcher: Fetcher) -> Dict[str, Any]:
    if source_name == "wikidata" and record.get("qid"):
        fetched = fetcher(wikidata_entity_data_url(str(record["qid"]).upper()), 15)
        return extract_wikidata_payload(source_name, record, fetched)
    fetched = fetcher(str(record.get("url")), 15)
    if "html" not in fetched.get("content_type", "").lower():
        raise ValueError("non_html_content")
    return extract_html_payload(source_name, record, fetched)


def raw_path_for(raw_root: Path, source_name: str, payload: Dict[str, Any]) -> Path:
    raw_id = payload.get("source_record_id") or payload.get("title") or payload.get("url") or source_name
    return raw_root / source_name / f"{safe_name(str(raw_id))}.json"


def default_frontier_path(source_name: str) -> Path:
    return FRONTIER_DIR / f"{source_name}_frontier.json"


def quality_fields_for_payload(payload: Dict[str, Any], quality_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    quality = score_page(payload, quality_context=quality_context)
    return {
        "quality_score": quality["score"],
        "quality_triage": quality["triage"],
        "quality_labels": quality["labels"],
        "quality_reasons": quality["reasons"],
        "quality_metrics": quality["metrics"],
    }


def quality_summary(items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    scored = [item for item in items if "quality_triage" in item]
    triage_counts: Counter[str] = Counter(str(item.get("quality_triage") or "unknown") for item in scored)
    reason_counts: Counter[str] = Counter()
    for item in scored:
        reason_counts.update(item.get("quality_reasons", []))
    return {
        "total": len(scored),
        "triage_counts": dict(sorted(triage_counts.items())),
        "top_reasons": dict(reason_counts.most_common(10)),
    }


def ingest_frontier(
    *,
    source_name: str,
    manifest: Dict[str, Any],
    frontier: Dict[str, Any],
    limit: int,
    delay: float,
    raw_root: Path = RAW_ROOT,
    report_path: Path | None = None,
    fetcher: Fetcher = fetch_url,
    min_text_length: int = MIN_TEXT_LENGTH,
    quality_report: bool = False,
    skip_rejected: bool = False,
) -> Dict[str, Any]:
    accepted = list(frontier.get("accepted", []))[: max(int(limit), 0)]
    report_items = []
    fetched_count = skipped_count = failed_count = 0
    quality_context = quality_context_from_manifest(manifest)

    for record in accepted:
        url = str(record.get("url") or "").strip()
        reason = "" if source_name == "wikidata" and record.get("qid") else skip_reason_for_url(url, manifest)
        if reason:
            skipped_count += 1
            report_items.append({"url": url, "status": "skipped", "reason": reason})
            continue
        try:
            payload = payload_for_record(source_name, record, fetcher)
            quality_fields = quality_fields_for_payload(payload, quality_context=quality_context) if quality_report else {}
            if skip_rejected and quality_fields.get("quality_triage") == "rejected":
                skipped_count += 1
                report_items.append({
                    "url": url,
                    "status": "skipped",
                    "reason": "skipped_quality_rejected",
                    "title": payload.get("title", ""),
                    "text_length": payload.get("text_length", 0),
                    **quality_fields,
                })
                continue
            if int(payload.get("text_length", 0) or 0) < min_text_length:
                skipped_count += 1
                report_items.append({
                    "url": url,
                    "status": "skipped",
                    "reason": "skipped_short_text",
                    "title": payload.get("title", ""),
                    "text_length": payload.get("text_length", 0),
                    **quality_fields,
                })
                continue
            output = raw_path_for(raw_root, source_name, payload)
            write_json(output, payload)
            fetched_count += 1
            report_items.append({
                "url": url,
                "status": "fetched",
                "reason": "ok",
                "title": payload.get("title", ""),
                "text_length": payload.get("text_length", 0),
                "saved_path": str(output),
                **quality_fields,
            })
        except Exception as exc:
            failed_count += 1
            report_items.append({"url": url, "status": "failed", "reason": type(exc).__name__, "error": str(exc)})
        if delay > 0:
            time.sleep(delay)

    report = {
        "source": source_name,
        "source_name": source_name,
        "source_registered": source_name in {"wikidata", "nasa", "esa"},
        "manifest_validation": manifest_validation_report(manifest, MANIFEST_DIR / f"{source_name}.json"),
        "mode": "manifest_frontier_raw_only",
        "generated_at": utc_now(),
        "frontier_accepted_count": len(frontier.get("accepted", [])),
        "requested_limit": int(limit),
        "fetched_count": fetched_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "raw_root": str(raw_root / source_name),
        "items": report_items,
    }
    if quality_report:
        report["quality_summary"] = quality_summary(report_items)
    write_json(report_path or REPORT_DIR / f"{source_name}_manifest_ingestion_report.json", report)
    return report


def summarize(report: Dict[str, Any]) -> str:
    return (
        f"{report['source_name']}: fetched={report['fetched_count']} "
        f"skipped={report['skipped_count']} failed={report['failed_count']} "
        f"frontier_accepted={report['frontier_accepted_count']}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch manifest frontier records as raw JSON only.")
    parser.add_argument("--source", required=True, choices=("wikidata", "nasa", "esa"))
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--frontier-json", default="")
    parser.add_argument("--report-json", default="")
    parser.add_argument("--delay", type=float, default=-1.0)
    parser.add_argument("--quality-report", action="store_true", help="Score fetched pages and include quality fields in the ingestion report.")
    parser.add_argument("--skip-rejected", action="store_true", help="Only with --quality-report: skip fetched pages whose quality triage is rejected.")
    parser.add_argument("--preflight-manifest", action="store_true", help="Validate the registered source manifest before ingest.")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.source, MANIFEST_DIR)
    validation = manifest_validation_report(manifest, MANIFEST_DIR / f"{args.source}.json")
    if args.preflight_manifest and not validation["passed"]:
        print(f"manifest validation failed: {validation['errors']}", file=sys.stderr)
        return 2
    frontier_path = Path(args.frontier_json) if args.frontier_json else default_frontier_path(args.source)
    frontier = read_json(frontier_path)
    delay = float(manifest.get("crawl_delay", 0) or 0) if args.delay < 0 else args.delay
    report = ingest_frontier(
        source_name=args.source,
        manifest=manifest,
        frontier=frontier,
        limit=args.limit,
        delay=delay,
        report_path=Path(args.report_json) if args.report_json else None,
        quality_report=args.quality_report,
        skip_rejected=args.skip_rejected,
    )
    print(summarize(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

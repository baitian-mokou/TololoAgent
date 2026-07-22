from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence
from urllib.parse import urljoin, urldefrag, urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MANIFEST_DIR = ROOT / "configs" / "source_manifests"
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/{qid}"
Fetcher = Callable[[str, int], str]

from src.source_quality.page_quality import score_page
from scripts.validate_source_manifests import validate_manifest


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs: Sequence[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_manifest(source_name: str, manifest_dir: Path = MANIFEST_DIR) -> Dict[str, Any]:
    path = manifest_dir / f"{source_name}.json"
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("source_name") != source_name:
        raise ValueError(f"Manifest {path} does not match source '{source_name}'")
    return manifest


def load_manifest_from_path(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError(f"Manifest {path} must be a JSON object")
    return manifest


def manifest_validation_report(manifest: Dict[str, Any], path: Path) -> Dict[str, Any]:
    errors = validate_manifest(manifest, Path(path))
    return {"passed": not errors, "errors": errors, "warnings": []}


def normalize_url(url: str, base_url: str = "") -> str:
    resolved = urljoin(base_url, str(url or "").strip())
    clean, _fragment = urldefrag(resolved)
    return clean.strip()


def hostname(url: str) -> str:
    return str(urlparse(str(url or "")).hostname or "").strip().lower()


def domain_allowed(url: str, allowed_domains: Sequence[str]) -> bool:
    host = hostname(url)
    for domain in allowed_domains:
        normalized = str(domain or "").strip().lower()
        if host == normalized or host.endswith(f".{normalized}"):
            return True
    return False


def path_contains(url: str, keywords: Sequence[str]) -> bool:
    if not keywords:
        return True
    haystack = f"{urlparse(url).path} {url}".lower()
    return any(str(keyword or "").lower() in haystack for keyword in keywords)


def path_has_any(url: str, keywords: Sequence[str]) -> bool:
    if not keywords:
        return False
    haystack = f"{urlparse(url).path} {url}".lower()
    return any(str(keyword or "").lower() in haystack for keyword in keywords)


def entity_seed_to_item(seed: Dict[str, Any]) -> Dict[str, Any]:
    qid = str(seed.get("qid") or "").strip().upper()
    entity = str(seed.get("entity") or qid).strip()
    url = WIKIDATA_ENTITY_URL.format(qid=qid) if qid else str(seed.get("url") or "").strip()
    return {
        "kind": "entity",
        "entity": entity,
        "qid": qid,
        "url": url,
        "depth": int(seed.get("depth", 0) or 0),
    }


def url_seed_to_item(url: str, depth: int = 0) -> Dict[str, Any]:
    return {"kind": "url", "url": normalize_url(url), "depth": depth}


def seed_items(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = [entity_seed_to_item(seed) for seed in manifest.get("seed_entities", [])]
    items.extend(url_seed_to_item(url) for url in manifest.get("seed_urls", []))
    return items


def classify_item(item: Dict[str, Any], manifest: Dict[str, Any], seen: set[str]) -> tuple[bool, str]:
    url = normalize_url(str(item.get("url") or ""))
    depth = int(item.get("depth", 0) or 0)
    identity = str(item.get("qid") or url).strip()
    if not url:
        return False, "missing_url"
    if identity in seen:
        return False, "duplicate"
    seen.add(identity)
    if depth > int(manifest.get("max_depth", 0) or 0):
        return False, "depth_exceeded"
    if not domain_allowed(url, manifest.get("allowed_domains", [])):
        return False, "domain_not_allowed"
    if path_has_any(url, manifest.get("exclude_path_keywords", [])):
        return False, "excluded_path"
    if not path_contains(url, manifest.get("include_path_keywords", [])):
        return False, "missing_include_keyword"
    return True, "accepted"


def item_record(item: Dict[str, Any], reason: str) -> Dict[str, Any]:
    record = {
        "kind": item.get("kind", "url"),
        "url": normalize_url(str(item.get("url") or "")),
        "depth": int(item.get("depth", 0) or 0),
        "reason": reason,
    }
    for key in ("entity", "qid"):
        if item.get(key):
            record[key] = item[key]
    return record


def quality_context_from_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_mode": manifest.get("source_mode", ""),
        "topic_taxonomy": manifest.get("topic_taxonomy", []),
        "quality_gate": manifest.get("quality_gate", {}),
        "quality_notes": manifest.get("quality_notes", ""),
    }


def add_quality_fields(
    record: Dict[str, Any],
    source_name: str,
    html: str = "",
    text: str = "",
    quality_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    candidate = {
        "url": record.get("url", ""),
        "title": record.get("entity") or record.get("qid") or record.get("url", ""),
        "text": text,
        "html": html,
        "source_name": source_name,
    }
    quality = score_page(candidate, quality_context=quality_context)
    record.update({
        "quality_input": "html" if html else ("text" if text else "metadata_only"),
        "quality_score": quality["score"],
        "quality_triage": quality["triage"],
        "quality_labels": quality["labels"],
        "quality_reasons": quality["reasons"],
        "quality_metrics": quality["metrics"],
    })
    return record


def quality_summary(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    scored = [record for record in records if "quality_triage" in record]
    triage_counts: Counter[str] = Counter(str(record.get("quality_triage") or "unknown") for record in scored)
    reason_counts: Counter[str] = Counter()
    for record in scored:
        reason_counts.update(record.get("quality_reasons", []))
    return {
        "total": len(scored),
        "triage_counts": dict(sorted(triage_counts.items())),
        "top_reasons": dict(reason_counts.most_common(10)),
    }


def extract_link_items(html: str, base_url: str, depth: int) -> List[Dict[str, Any]]:
    parser = LinkExtractor()
    parser.feed(html or "")
    return [url_seed_to_item(normalize_url(href, base_url), depth + 1) for href in parser.hrefs]


def fetch_html(url: str, timeout: int = 8) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "tololo-frontier-preview/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = str(response.headers.get("Content-Type") or "").lower()
        if "html" not in content_type:
            return ""
        return response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def fetch_link_items(
    accepted: Sequence[Dict[str, Any]],
    timeout: int = 8,
    fetcher: Fetcher = fetch_html,
    delay: float = 0.0,
) -> List[Dict[str, Any]]:
    discovered: List[Dict[str, Any]] = []
    for record in accepted:
        if record.get("kind") == "entity":
            continue
        html = fetcher(record["url"], timeout)
        discovered.extend(extract_link_items(html, record["url"], int(record.get("depth", 0))))
        if delay > 0:
            time.sleep(delay)
    return discovered


def build_frontier_preview(
    manifest: Dict[str, Any],
    limit: int,
    fetch_links: bool = False,
    fetcher: Fetcher = fetch_html,
    quality_score: bool = False,
    custom_manifest: bool = False,
    manifest_path: Path | None = None,
    validation: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if custom_manifest and fetch_links:
        fetch_links = False
        validation = validation or manifest_validation_report(manifest, manifest_path or Path(f"{manifest.get('source_name', 'manifest')}.json"))
        validation.setdefault("warnings", []).append("custom_manifest_fetch_links_disabled_offline_preview")
    effective_limit = min(max(int(limit), 0), int(manifest.get("max_pages_per_run", 0) or limit or 0))
    max_discovery_fetch_pages = int(manifest.get("max_discovery_fetch_pages", 25))
    accepted: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    queue = seed_items(manifest)
    index = 0
    discovery_fetches = 0

    while index < len(queue):
        item = queue[index]
        index += 1
        is_accepted, reason = classify_item(item, manifest, seen)
        if not is_accepted:
            skipped.append(item_record(item, reason))
            continue
        if len(accepted) >= effective_limit:
            skipped.append(item_record(item, "limit_reached"))
            continue
        record = item_record(item, reason)
        if quality_score:
            add_quality_fields(
                record,
                str(manifest.get("source_name") or ""),
                quality_context=quality_context_from_manifest(manifest),
            )
        accepted.append(record)
        can_fetch_more = max_discovery_fetch_pages > 0 and discovery_fetches < max_discovery_fetch_pages
        if fetch_links and can_fetch_more and int(item.get("depth", 0) or 0) < int(manifest.get("max_depth", 0) or 0):
            try:
                discovery_fetches += 1
                queue.extend(
                    fetch_link_items(
                        [accepted[-1]],
                        fetcher=fetcher,
                        delay=float(manifest.get("crawl_delay", 0) or 0),
                    )
                )
            except Exception as exc:
                skipped.append({**accepted[-1], "reason": "fetch_links_failed", "error": str(exc)})

    report = {
        "source_name": manifest.get("source_name"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "network_access": bool(fetch_links),
        "source_registered": not custom_manifest,
        "manifest_validation": validation or manifest_validation_report(
            manifest,
            manifest_path or MANIFEST_DIR / f"{manifest.get('source_name', 'manifest')}.json",
        ),
        "limit": effective_limit,
        "accepted_count": len(accepted),
        "skipped_count": len(skipped),
        "discovery_fetches": discovery_fetches,
        "limit_reached": len(accepted) >= effective_limit if effective_limit else False,
        "manifest": {
            "allowed_domains": manifest.get("allowed_domains", []),
            "max_depth": manifest.get("max_depth", 0),
            "max_pages_per_run": manifest.get("max_pages_per_run", 0),
            "max_discovery_fetch_pages": max_discovery_fetch_pages,
            "crawl_delay": manifest.get("crawl_delay", 0),
            "notes": manifest.get("notes", ""),
            "source_mode": manifest.get("source_mode", ""),
            "topic_taxonomy": manifest.get("topic_taxonomy", []),
            "quality_gate": manifest.get("quality_gate", {}),
            "quality_notes": manifest.get("quality_notes", ""),
        },
        "accepted": accepted,
        "skipped": skipped,
    }
    if quality_score:
        report["quality_summary"] = quality_summary(accepted)
    return report


def summarize(report: Dict[str, Any]) -> str:
    reasons: Dict[str, int] = {}
    for item in report["skipped"]:
        reason = str(item.get("reason") or "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1
    return (
        f"{report['source_name']}: accepted={report['accepted_count']} "
        f"skipped={report['skipped_count']} network={report['network_access']} "
        f"skip_reasons={reasons}"
    ) + (f" quality={report['quality_summary']['triage_counts']}" if report.get("quality_summary") else "")


def write_json(path: str, payload: Dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Preview source frontier candidates without writing ingestion data.")
    parser.add_argument("--source", choices=("wikidata", "nasa", "esa"))
    parser.add_argument("--manifest", default="", help="Preview an unregistered manifest JSON offline.")
    parser.add_argument("--preflight-manifest", action="store_true", help="Validate the manifest before previewing.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json-out", default="")
    parser.add_argument("--fetch-links", action="store_true", help="Explicitly fetch accepted seed pages and preview linked URLs.")
    parser.add_argument("--quality-score", action="store_true", help="Add local page-quality score fields to accepted candidates.")
    args = parser.parse_args(argv)

    if not args.source and not args.manifest:
        parser.error("one of --source or --manifest is required")
    if args.source and args.manifest:
        parser.error("--source and --manifest are mutually exclusive")

    custom_manifest = bool(args.manifest)
    manifest_path = Path(args.manifest) if args.manifest else MANIFEST_DIR / f"{args.source}.json"
    manifest = load_manifest_from_path(manifest_path) if custom_manifest else load_manifest(str(args.source))
    validation = manifest_validation_report(manifest, manifest_path)
    if (args.preflight_manifest or custom_manifest) and not validation["passed"]:
        print(f"manifest validation failed: {validation['errors']}", file=sys.stderr)
        return 2
    report = build_frontier_preview(
        manifest,
        args.limit,
        fetch_links=args.fetch_links,
        quality_score=args.quality_score,
        custom_manifest=custom_manifest,
        manifest_path=manifest_path,
        validation=validation,
    )
    if args.json_out:
        write_json(args.json_out, report)
    print(summarize(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.nasa_specific_content_url_preview_phase99 import classify_page


ALLOWED_HOSTS = {"science.nasa.gov", "images-api.nasa.gov", "images-assets.nasa.gov", "api.nasa.gov"}


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase100") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def official_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.netloc.lower() in ALLOWED_HOSTS


def strategy_entries(*, limit_per_entry: int = 5) -> List[Dict[str, Any]]:
    limit = min(max(limit_per_entry, 1), 5)
    return [
        {
            "strategy": "science_wp_rest_posts",
            "url": f"https://science.nasa.gov/wp-json/wp/v2/posts?per_page={limit}&search=Juno",
            "limit": limit,
        },
        {
            "strategy": "science_sitemap_posts",
            "url": "https://science.nasa.gov/post-sitemap.xml",
            "limit": limit,
        },
        {
            "strategy": "nasa_images_api",
            "url": f"https://images-api.nasa.gov/search?q=Juno&media_type=image&page_size={limit}",
            "limit": limit,
        },
    ]


def fetch_entry(entry: Dict[str, Any], *, timeout: int = 15) -> Dict[str, Any]:
    url = entry["url"]
    request = urllib.request.Request(url, headers={"User-Agent": "TololoAgent Phase100 evaluation-only probe"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(750_000)
            text = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            content_type = response.headers.get("content-type", "")
            payload: Any = text
            if "json" in content_type:
                try:
                    payload = json.loads(text)
                except Exception:
                    payload = text
            return {
                "strategy": entry["strategy"],
                "url": url,
                "status": "http_200" if response.status == 200 else f"http_{response.status}",
                "status_code": response.status,
                "content_type": content_type,
                "payload": payload,
            }
    except urllib.error.HTTPError as exc:
        return {
            "strategy": entry["strategy"],
            "url": url,
            "status": f"http_{exc.code}",
            "status_code": exc.code,
            "content_type": "",
            "payload": "",
            "failure_reason": str(exc),
        }
    except Exception as exc:
        return {
            "strategy": entry["strategy"],
            "url": url,
            "status": "failed",
            "status_code": 0,
            "content_type": "",
            "payload": "",
            "failure_reason": str(exc),
        }


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(str(text)))).strip()


def item_text(item: Dict[str, Any]) -> str:
    parts = []
    for key in ("content", "excerpt", "description", "summary"):
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("rendered")
        if isinstance(value, str):
            parts.append(strip_html(value))
    return " ".join(part for part in parts if part)


def item_title(item: Dict[str, Any], fallback: str = "NASA") -> str:
    value = item.get("title") or item.get("name") or item.get("nasa_id")
    if isinstance(value, dict):
        value = value.get("rendered")
    return strip_html(value or fallback)


def preview_from_item(item: Dict[str, Any]) -> Dict[str, Any] | None:
    body = item_text(item)
    if not body:
        return None
    classified = classify_page(f"<main>{body}</main>")
    if classified["status"] == "rejected_for_review":
        return None
    title = item_title(item)
    url = str(item.get("link") or item.get("href") or item.get("url") or "")
    return {
        "source": "nasa",
        "source_id": "nasa",
        "title": title,
        "url": url,
        "body_excerpt": classified["text"][:700],
        "structured_fields": sorted(k for k in item if k in {"title", "link", "content", "excerpt", "description", "summary", "nasa_id"}),
        "quality_flags": ["phase100_endpoint_preview", classified["status"]],
        "provenance": {"phase": "Phase100", "source_url": url},
    }


def json_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("collection", {}).get("items"), list):
            out = []
            for item in payload["collection"]["items"]:
                data = item.get("data", [{}])[0] if isinstance(item, dict) else {}
                if isinstance(data, dict):
                    data = dict(data)
                    data["href"] = item.get("href", "")
                    out.append(data)
            return out
        return [payload]
    return []


def sitemap_items(payload: Any, *, limit: int) -> List[Dict[str, Any]]:
    text = str(payload)
    urls = re.findall(r"<loc>(.*?)</loc>", text)[:limit]
    return [{"title": url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title(), "link": url, "summary": ""} for url in urls]


def judge_entry(result: Dict[str, Any], *, limit: int) -> Dict[str, Any]:
    status_code = int(result.get("status_code") or 0)
    auth_required = status_code in {401, 403}
    if auth_required:
        verdict = "blocked_auth_required"
        items: List[Dict[str, Any]] = []
    elif result.get("status") != "http_200":
        verdict = "blocked_fetch_failed"
        items = []
    elif "xml" in str(result.get("content_type", "")).lower() or result["strategy"].endswith("sitemap_posts"):
        items = sitemap_items(result.get("payload", ""), limit=limit)
        verdict = "url_list_only_needs_followup_fetch" if items else "no_items_found"
    else:
        items = json_items(result.get("payload"))[:limit]
        verdict = "no_items_found"
    previews = [preview for item in items[:limit] if (preview := preview_from_item(item))]
    if previews:
        verdict = "usable_structured_body"
    fields = sorted({key for item in items[:limit] for key in item.keys()})
    return {
        "strategy": result.get("strategy"),
        "url": result.get("url"),
        "status": result.get("status"),
        "status_code": status_code,
        "content_type": result.get("content_type", ""),
        "sample_count": len(items[:limit]),
        "body_field_available": bool(previews),
        "structured_fields": fields[:20],
        "auth_required": auth_required,
        "suitability_verdict": verdict,
        "preview_candidates": previews[:limit],
        "failure_reason": result.get("failure_reason", ""),
    }


def build_report(*, entry_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    candidates = [candidate for entry in entry_reports for candidate in entry.get("preview_candidates", [])][:5]
    return {
        "phase": "Phase 100",
        "mode": "nasa_source_endpoint_api_sitemap_strategy_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry_count": len(entry_reports),
        "entry_verdicts": {entry.get("strategy", ""): entry.get("suitability_verdict", "") for entry in entry_reports},
        "entry_reports": entry_reports,
        "candidate_count": len(candidates),
        "reviewable_candidates": candidates,
        "quality_verdict": "nasa_endpoint_strategy_found_structured_candidates" if candidates else "nasa_endpoint_strategy_blocked_or_url_list_only",
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
        "# Phase100 NASA Source Endpoint/API/Sitemap Strategy Preview",
        "",
        f"- quality_verdict: `{report['quality_verdict']}`",
        f"- entry_count: {report['entry_count']}",
        f"- candidate_count: {report['candidate_count']}",
        f"- production_ready: `{report['production_ready']}`",
        "",
        "| strategy | status | samples | body_field | verdict |",
        "|---|---|---:|---|---|",
    ]
    for entry in report["entry_reports"]:
        lines.append(
            f"| {entry['strategy']} | {entry['status']} | {entry['sample_count']} | "
            f"{entry['body_field_available']} | `{entry['suitability_verdict']}` |"
        )
    lines.append("\nNext: use usable structured endpoint candidates for review preview only; no apply or ingest.")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe NASA official source endpoint/API/sitemap strategies.")
    parser.add_argument("--limit-per-entry", type=int, default=5)
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase100"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_source_endpoint_strategy_preview_phase100.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_md = Path(args.out_md)
    out_json = out_dir / "nasa_source_endpoint_strategy_preview_phase100.json"
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase100 or docs/", file=sys.stderr)
        return 2
    entries = strategy_entries(limit_per_entry=args.limit_per_entry)
    entry_reports = [judge_entry(fetch_entry(entry), limit=entry["limit"]) for entry in entries]
    report = build_report(entry_reports=entry_reports)
    write_json(out_json, report)
    write_text(out_dir / "nasa_source_endpoint_strategy_preview_phase100.md", render_report(report))
    write_text(out_md, render_report(report))
    print(f"quality={report['quality_verdict']} entries={report['entry_count']} candidates={report['candidate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

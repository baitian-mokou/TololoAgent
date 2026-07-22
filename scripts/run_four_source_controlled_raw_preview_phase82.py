from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.plan_four_source_crawler_scope_phase81 import ALLOWED_HOSTS, allowed_url, ensure_url
from scripts.select_deduped_frontier_candidates import canonical_url, normalized_title


LIMITS = {"zh_wikipedia": 3, "nasa": 17, "esa": 15, "wikidata": 25}
TOTAL_LIMIT = 60


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase82") or (allow_docs and rel.parts[:1] == ("docs",))


def clean_text(value: str, limit: int = 900) -> str:
    text = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", value, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def fetch_excerpt(url: str, timeout: int = 12) -> Dict[str, Any]:
    req = Request(url, headers={"User-Agent": "TololoAgent phase82 preview"})
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read(200_000).decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
        return {"status_code": getattr(resp, "status", 200), "text_excerpt": clean_text(body)}


def rows(path: Path, key: str = "candidate_statuses") -> List[Dict[str, Any]]:
    payload = read_json(path)
    values = payload.get(key, []) if isinstance(payload, dict) else []
    return values if isinstance(values, list) else []


def phase81_candidates(path: Path, source_id: str) -> List[Dict[str, Any]]:
    payload = read_json(path)
    source = payload.get("sources", {}).get(source_id, {}) if isinstance(payload, dict) else {}
    values = source.get("sample_candidates", [])
    return values if isinstance(values, list) else []


def local_raw_excerpt(path_text: str) -> str:
    if not str(path_text or "").strip():
        return ""
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    payload = read_json(path)
    if not isinstance(payload, dict) or not payload:
        return ""
    text = payload.get("text") or payload.get("content") or payload.get("extract") or payload.get("summary") or json.dumps(payload, ensure_ascii=False)
    return clean_text(str(text))


def make_item(source_id: str, row: Dict[str, Any], reason: str) -> Dict[str, Any]:
    title = str(row.get("title") or row.get("entity") or row.get("page_title") or row.get("qid") or "")
    url = ensure_url(str(row.get("url") or row.get("source_url") or ""), source_id)
    qid = str(row.get("qid") or "")
    if source_id == "wikidata" and qid:
        url = url or f"https://www.wikidata.org/wiki/{qid}"
    return {"source": source_id, "title": title, "id": qid or title, "url": url, "entity_id": qid, "reason": reason, "assessment": row}


def dedup(items: Iterable[Dict[str, Any]], source_id: str, limit: int) -> tuple[List[Dict[str, Any]], int, int]:
    selected: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    duplicates = rejected = 0
    for item in items:
        if len(selected) >= limit:
            break
        if not allowed_url(source_id, item["url"]):
            rejected += 1
            continue
        url_key = canonical_url(item["url"])
        title_key = normalized_title(item["title"])
        if (url_key and url_key in seen_urls) or (title_key and title_key in seen_titles):
            duplicates += 1
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        selected.append(item)
    return selected, duplicates, rejected


def select_candidates(root: Path) -> Dict[str, Dict[str, Any]]:
    phase81 = root / "evaluation" / "four_source_expansion" / "phase81" / "four_source_crawler_scope_expansion_phase81.json"
    zh = [make_item("zh_wikipedia", row, "phase81_accepted") for row in phase81_candidates(phase81, "zh_wikipedia")]
    nasa_report = root / "evaluation" / "four_source_expansion" / "nasa_frontier_refresh_phase58.json"
    nasa = [make_item("nasa", row, "phase81_review_needed_official") for row in rows(nasa_report, "review_needed_candidates")]
    esa67 = rows(root / "evaluation" / "four_source_expansion" / "esa_controlled_assessment_phase67.json")
    esa68 = rows(root / "evaluation" / "four_source_expansion" / "esa_raw_preview_batch_phase68.json")
    esa_rows = [row for row in esa67 if row.get("status") == "accepted_for_package"] + [row for row in esa67 + esa68 if row.get("status") == "review_needed"][:6]
    esa = [make_item("esa", row, "phase67_68_accepted_or_review_needed") | {"raw_path": str(row.get("raw_path") or row.get("raw_preview_path") or "")} for row in esa_rows]
    wiki_rows = [row for row in rows(root / "evaluation" / "four_source_expansion" / "wikidata_controlled_assessment_phase74.json") if row.get("status") == "accepted_for_package"]
    wikidata = [make_item("wikidata", row, "phase74_accepted") | {"raw_path": str(row.get("raw_path") or "")} for row in wiki_rows]
    out: Dict[str, Dict[str, Any]] = {}
    total = 0
    for source_id, values in {"zh_wikipedia": zh, "nasa": nasa, "esa": esa, "wikidata": wikidata}.items():
        limit = min(LIMITS[source_id], TOTAL_LIMIT - total)
        selected, duplicates, rejected = dedup(values, source_id, limit)
        total += len(selected)
        out[source_id] = {"selected": selected, "duplicates": duplicates, "rejected": rejected}
    return out


def preview_item(item: Dict[str, Any]) -> Dict[str, Any]:
    source_id = item["source"]
    excerpt = local_raw_excerpt(item.get("raw_path", ""))
    fetched = bool(excerpt)
    status = "local_preview"
    failure_reason = ""
    if not excerpt and source_id in {"nasa", "esa"}:
        try:
            fetched_payload = fetch_excerpt(item["url"])
            excerpt = fetched_payload["text_excerpt"]
            fetched = True
            status = f"http_{fetched_payload['status_code']}"
        except (OSError, URLError, TimeoutError, ValueError) as exc:
            status = "failed"
            failure_reason = type(exc).__name__
    elif source_id == "zh_wikipedia":
        excerpt = local_raw_excerpt(str(ROOT / "data" / "raw_json" / "zh_wikipedia" / f"{item['title']}.json"))
        fetched = bool(excerpt)
        status = "local_preview" if fetched else "failed"
        failure_reason = "" if fetched else "missing_local_raw"
    elif source_id == "wikidata":
        assessment = item.get("assessment", {}) if isinstance(item.get("assessment"), dict) else {}
        excerpt = clean_text(json.dumps({k: assessment.get(k) for k in ("qid", "title", "url", "reason", "has_local_raw", "has_local_materialized_pair")}, ensure_ascii=False))
        fetched = bool(excerpt)
        status = "assessment_preview" if fetched else "failed"
        failure_reason = "" if fetched else "missing_assessment"
    return {
        **{key: item.get(key, "") for key in ("source", "title", "id", "url", "entity_id", "reason")},
        "fetched": fetched,
        "status": status,
        "failure_reason": failure_reason,
        "text_excerpt": excerpt,
        "claims_subset": excerpt[:400] if source_id == "wikidata" else "",
        "quality_flags": {
            "allowlisted": allowed_url(source_id, item["url"]),
            "has_excerpt": bool(excerpt),
            "evaluation_only": True,
        },
    }


def build_report(root: Path = ROOT) -> Dict[str, Any]:
    selected = select_candidates(root)
    previews: List[Dict[str, Any]] = []
    for payload in selected.values():
        previews.extend(preview_item(item) for item in payload["selected"])
    counts = Counter((item["source"], "succeeded" if item["fetched"] else "failed") for item in previews)
    per_source = {}
    for source_id, payload in selected.items():
        attempted = len(payload["selected"])
        succeeded = counts.get((source_id, "succeeded"), 0)
        per_source[source_id] = {
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": counts.get((source_id, "failed"), 0),
            "rejected": payload["rejected"],
            "duplicates": payload["duplicates"],
            "recommended_next_batch_size": succeeded,
        }
    return {
        "phase": "Phase 82",
        "mode": "four_source_controlled_raw_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_limit": TOTAL_LIMIT,
        "per_source_limits": LIMITS,
        "attempted": len(previews),
        "succeeded": sum(item["succeeded"] for item in per_source.values()),
        "failed": sum(item["failed"] for item in per_source.values()),
        "rejected": sum(item["rejected"] for item in per_source.values()),
        "duplicates": sum(item["duplicates"] for item in per_source.values()),
        "per_source": per_source,
        "raw_previews": previews,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def render_md(report: Dict[str, Any]) -> str:
    lines = [
        "# Four-source controlled raw preview",
        "",
        f"- attempted: `{report['attempted']}`",
        f"- succeeded: `{report['succeeded']}`",
        f"- failed: `{report['failed']}`",
        f"- active_source: `{report['active_source']}`",
        "",
        "| source | attempted | succeeded | failed | rejected | duplicates | next_batch |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for source, item in report["per_source"].items():
        lines.append(f"| {source} | {item['attempted']} | {item['succeeded']} | {item['failed']} | {item['rejected']} | {item['duplicates']} | {item['recommended_next_batch_size']} |")
    lines.extend(["", "Boundaries: evaluation/docs only; no data/raw_json, data/triples, Chroma, Neo4j, source switch, or clear ingestion call.", ""])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded four-source raw preview under evaluation only.")
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase82" / "four_source_controlled_raw_preview_phase82.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_controlled_raw_preview_phase82.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase82 or docs/", file=sys.stderr)
        return 2
    report = build_report()
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"attempted={report['attempted']} succeeded={report['succeeded']} failed={report['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

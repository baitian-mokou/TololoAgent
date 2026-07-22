from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.select_deduped_frontier_candidates import canonical_url, normalized_title


LIMITS = {"zh_wikipedia": 80, "nasa": 100, "esa": 80, "wikidata": 100}
LIVE_FETCH_MAX = 30
ALLOWED_HOSTS = {
    "zh_wikipedia": ("zh.wikipedia.org",),
    "nasa": ("science.nasa.gov", "www.nasa.gov", "nasa.gov", "nssdc.gsfc.nasa.gov"),
    "esa": ("www.esa.int", "esa.int"),
    "wikidata": ("www.wikidata.org", "wikidata.org", "query.wikidata.org"),
}


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase81") or (allow_docs and rel.parts[:1] == ("docs",))


def ensure_url(value: str, source_id: str) -> str:
    value = str(value or "").strip()
    if source_id == "zh_wikipedia" and value and not value.startswith(("http://", "https://")):
        return "https://zh.wikipedia.org/wiki/" + value.replace(" ", "_")
    if value and not value.startswith(("http://", "https://")):
        return "https://" + value.lstrip("/")
    return value


def allowed_url(source_id: str, url: str) -> bool:
    parsed = urlparse(ensure_url(url, source_id))
    host = parsed.netloc.lower()
    return parsed.scheme == "https" and any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_HOSTS[source_id])


def candidate(source_id: str, row: Dict[str, Any], status: str = "review_needed") -> Dict[str, Any]:
    title = str(row.get("title") or row.get("entity") or row.get("page_title") or row.get("qid") or "")
    url = ensure_url(str(row.get("url") or row.get("source_url") or ""), source_id)
    if source_id == "wikidata" and not url and row.get("qid"):
        url = f"https://www.wikidata.org/wiki/{row['qid']}"
    if source_id == "zh_wikipedia" and not url and title:
        url = ensure_url(title, source_id)
    return {
        "source_id": source_id,
        "status": status,
        "title": title,
        "url": url,
        "reason": row.get("reason") or row.get("quality_triage") or row.get("status") or "local_preview_candidate",
    }


def rows_from_report(path: Path) -> List[Dict[str, Any]]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        return []
    rows: List[Dict[str, Any]] = []
    for key, status in (
        ("accepted_candidates", "accepted_for_raw_preview"),
        ("review_needed_candidates", "review_needed"),
        ("candidate_statuses", ""),
        ("accepted", "accepted_for_raw_preview"),
    ):
        values = payload.get(key)
        if not isinstance(values, list):
            continue
        for row in values:
            if not isinstance(row, dict):
                continue
            rows.append({**row, "_status": status or row.get("status", "review_needed")})
    return rows


def zh_rows(raw_root: Path) -> List[Dict[str, Any]]:
    rows = []
    for path in sorted(raw_root.glob("*.json")) if raw_root.exists() else []:
        payload = read_json(path)
        title = str(payload.get("title") or path.stem) if isinstance(payload, dict) else path.stem
        rows.append({"title": title, "url": f"https://zh.wikipedia.org/wiki/{title}", "_status": "accepted_for_raw_preview"})
    return rows


def dedup_and_classify(source_id: str, rows: Iterable[Dict[str, Any]], limit: int) -> Dict[str, Any]:
    selected: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    duplicates = allowlist_rejected = 0
    for row in rows:
        if len(selected) >= limit:
            break
        item = candidate(source_id, row, row.get("_status", "review_needed"))
        url_key = canonical_url(item["url"])
        title_key = normalized_title(item["title"])
        if not item["url"] or not allowed_url(source_id, item["url"]):
            allowlist_rejected += 1
            rejected.append({**item, "status": "rejected", "reason": "outside_allowlist"})
            continue
        if (url_key and url_key in seen_urls) or (title_key and title_key in seen_titles):
            duplicates += 1
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        selected.append(item)
    counts = Counter(row["status"] for row in selected)
    recommended = min(LIVE_FETCH_MAX, counts.get("review_needed", 0) or counts.get("accepted_for_raw_preview", 0))
    return {
        "source_id": source_id,
        "candidate_limit": limit,
        "selected_candidates": len(selected),
        "accepted_for_raw_preview": counts.get("accepted_for_raw_preview", 0) + counts.get("accepted_for_package", 0),
        "review_needed": counts.get("review_needed", 0),
        "rejected": counts.get("rejected", 0) + len(rejected),
        "failed": counts.get("failed", 0),
        "duplicates_excluded": duplicates,
        "allowlist_rejected": allowlist_rejected,
        "recommended_next_batch_size": recommended,
        "allowlist": list(ALLOWED_HOSTS[source_id]),
        "sample_candidates": selected[:10],
    }


def build_report(root: Path = ROOT) -> Dict[str, Any]:
    sources = {
        "zh_wikipedia": zh_rows(root / "data" / "raw_json" / "zh_wikipedia"),
        "nasa": rows_from_report(root / "evaluation" / "four_source_expansion" / "nasa_frontier_refresh_phase58.json"),
        "esa": rows_from_report(root / "evaluation" / "four_source_expansion" / "esa_controlled_assessment_phase67.json")
        + rows_from_report(root / "evaluation" / "four_source_expansion" / "esa_raw_preview_batch_phase68.json"),
        "wikidata": rows_from_report(root / "evaluation" / "four_source_expansion" / "wikidata_controlled_assessment_phase74.json"),
    }
    per_source = {source: dedup_and_classify(source, rows, LIMITS[source]) for source, rows in sources.items()}
    return {
        "phase": "Phase 81",
        "mode": "four_source_crawler_scope_expansion_guarded_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run_preview_default": True,
        "live_fetch_attempted": False,
        "live_fetch_max_per_source": LIVE_FETCH_MAX,
        "per_source_limits": LIMITS,
        "sources": per_source,
        "summary": {
            "candidate_count": sum(item["selected_candidates"] for item in per_source.values()),
            "accepted_for_raw_preview": sum(item["accepted_for_raw_preview"] for item in per_source.values()),
            "review_needed": sum(item["review_needed"] for item in per_source.values()),
            "rejected": sum(item["rejected"] for item in per_source.values()),
            "duplicates_excluded": sum(item["duplicates_excluded"] for item in per_source.values()),
        },
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def render_md(report: Dict[str, Any]) -> str:
    lines = [
        "# Four-source crawler scope expansion preview",
        "",
        f"- dry_run_preview_default: `{report['dry_run_preview_default']}`",
        f"- live_fetch_attempted: `{report['live_fetch_attempted']}`",
        f"- active_source: `{report['active_source']}`",
        "",
        "| source | limit | selected | accepted_for_raw_preview | review_needed | rejected | duplicates | recommended_next_batch |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for source, item in report["sources"].items():
        lines.append(
            f"| {source} | {item['candidate_limit']} | {item['selected_candidates']} | {item['accepted_for_raw_preview']} | "
            f"{item['review_needed']} | {item['rejected']} | {item['duplicates_excluded']} | {item['recommended_next_batch_size']} |"
        )
    lines.extend(
        [
            "",
            "Boundaries: no data/raw_json, data/triples, Chroma, or Neo4j writes; NASA/ESA/Wikidata remain disabled.",
            "Next: review this scope, then choose bounded raw preview batches per source.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan guarded four-source crawler scope expansion.")
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase81" / "four_source_crawler_scope_expansion_phase81.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_crawler_scope_expansion_phase81.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase81 or docs/", file=sys.stderr)
        return 2
    report = build_report()
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"candidates={report['summary']['candidate_count']} review={report['summary']['review_needed']} duplicates={report['summary']['duplicates_excluded']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

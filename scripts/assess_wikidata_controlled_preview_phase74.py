from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.materialize_manifest_raw_records import safe_name
from scripts.select_deduped_frontier_candidates import canonical_url, normalized_title


SOURCE_ID = "wikidata"


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
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return relative.parts[:2] == ("evaluation", "four_source_expansion") or (allow_docs and relative.parts[:1] == ("docs",))


def frontier_rows(frontier_json: Path) -> List[Dict[str, Any]]:
    payload = read_json(frontier_json)
    rows = payload.get("accepted", []) if isinstance(payload, dict) else []
    return rows if isinstance(rows, list) else []


def raw_by_qid(raw_root: Path) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for path in sorted(raw_root.glob("*.json")) if raw_root.exists() else []:
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        record = payload.get("record", {}) if isinstance(payload.get("record"), dict) else payload
        qid = str(record.get("qid") or payload.get("qid") or path.stem)
        rows[qid] = {**payload, "_raw_path": str(path)}
    return rows


def materialized_titles(triples_root: Path) -> set[str]:
    titles: set[str] = set()
    for path in sorted(triples_root.glob("*_triples.json")) if triples_root.exists() else []:
        title = path.name.removesuffix("_triples.json")
        if (triples_root / f"{title}_narratives.json").exists():
            titles.add(normalized_title(title))
    return titles


def prior_bad_fingerprints(paths: Sequence[Path]) -> tuple[set[str], set[str]]:
    urls: set[str] = set()
    titles: set[str] = set()
    for path in paths:
        report = read_json(path)
        for row in report.get("candidate_statuses", []) if isinstance(report, dict) else []:
            if row.get("status") not in {"rejected", "failed", "duplicate_skipped"}:
                continue
            url = canonical_url(str(row.get("url") or ""))
            title = normalized_title(str(row.get("title") or row.get("entity") or ""))
            if url:
                urls.add(url)
            if title:
                titles.add(title)
    return urls, titles


def raw_ready(raw: Dict[str, Any]) -> bool:
    record = raw.get("record", {}) if isinstance(raw.get("record"), dict) else raw
    return bool(record.get("triples")) and bool(record.get("narratives"))


def assess_wikidata(
    *,
    frontier_json: Path,
    raw_root: Path,
    triples_root: Path,
    limit: int = 50,
    exclude_report_paths: Sequence[Path] = (),
) -> Dict[str, Any]:
    raws = raw_by_qid(raw_root)
    existing_titles = materialized_titles(triples_root)
    bad_urls, bad_titles = prior_bad_fingerprints(exclude_report_paths)
    statuses: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    duplicates = bad_excluded = 0
    for row in frontier_rows(frontier_json):
        if len(statuses) >= min(limit, 50):
            break
        qid = str(row.get("qid") or "")
        title = str(row.get("entity") or row.get("title") or qid)
        url = str(row.get("url") or "")
        url_key = canonical_url(url)
        title_key = normalized_title(title)
        if url_key in bad_urls or title_key in bad_titles:
            bad_excluded += 1
            continue
        if (url_key and url_key in seen_urls) or (title_key and title_key in seen_titles):
            duplicates += 1
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        raw = raws.get(qid)
        has_raw = bool(raw)
        has_materialized = title_key in existing_titles
        if has_raw and raw_ready(raw):
            status = "accepted_for_package"
            reason = "local_entity_raw_has_triples_and_narratives"
        elif has_materialized:
            status = "accepted_for_package"
            reason = "local_materialized_preview_exists"
        elif has_raw:
            status = "review_needed"
            reason = "local_raw_missing_triples_or_narratives"
        else:
            status = "review_needed"
            reason = "local_raw_missing_preview_only"
        statuses.append(
            {
                "status": status,
                "reason": reason,
                "qid": qid,
                "title": title,
                "url": url,
                "has_local_raw": has_raw,
                "has_local_materialized_pair": has_materialized,
                "raw_path": raw.get("_raw_path", "") if isinstance(raw, dict) else "",
            }
        )
    counts = Counter(row["status"] for row in statuses)
    return {
        "phase": "Phase 74",
        "mode": "wikidata_controlled_source_assessment_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_id": SOURCE_ID,
        "selected": len(statuses),
        "accepted_for_package": counts.get("accepted_for_package", 0),
        "review_needed": counts.get("review_needed", 0),
        "rejected": counts.get("rejected", 0),
        "failed": counts.get("failed", 0),
        "duplicates_excluded": duplicates,
        "prior_bad_excluded": bad_excluded,
        "candidate_statuses": statuses,
        "reason_counts": dict(Counter(row.get("reason", "") for row in statuses)),
        "recommended_next_package_size": counts.get("accepted_for_package", 0),
        "network_attempted": False,
        "formal_raw_write": False,
        "formal_triples_write": False,
        "formal_narratives_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
    }


def render_md(report: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Wikidata controlled source assessment preview",
            "",
            f"- selected: `{report['selected']}`",
            f"- accepted_for_package: `{report['accepted_for_package']}`",
            f"- review_needed: `{report['review_needed']}`",
            f"- rejected: `{report['rejected']}`",
            f"- failed: `{report['failed']}`",
            f"- recommended_next_package_size: `{report['recommended_next_package_size']}`",
            f"- network_attempted: `{report['network_attempted']}`",
            f"- active_source_unchanged: `{report['active_source_unchanged']}`",
            f"- wikidata_registry: `{report['registry'].get('wikidata')}`",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assess Wikidata controlled preview candidates without formal writes.")
    parser.add_argument("--frontier-json", default=str(ROOT / "evaluation" / "source_frontiers" / "wikidata_frontier.json"))
    parser.add_argument("--raw-root", default=str(ROOT / "data" / "raw_json" / SOURCE_ID))
    parser.add_argument("--triples-root", default=str(ROOT / "data" / "triples" / SOURCE_ID))
    parser.add_argument("--exclude-report-json", action="append", default=[])
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "wikidata_controlled_assessment_phase74.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "wikidata_controlled_assessment_phase74.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = assess_wikidata(
        frontier_json=Path(args.frontier_json),
        raw_root=Path(args.raw_root),
        triples_root=Path(args.triples_root),
        limit=args.limit,
        exclude_report_paths=[Path(p) for p in args.exclude_report_json],
    )
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"accepted={report['accepted_for_package']} review={report['review_needed']} rejected={report['rejected']} failed={report['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

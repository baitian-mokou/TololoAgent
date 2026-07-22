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
from scripts.ingest_manifest_frontier import quality_fields_for_payload
from scripts.select_deduped_frontier_candidates import canonical_url, normalized_title


SOURCE_ID = "esa"


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


def raw_lookup(raw_roots: Sequence[Path]) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for root in raw_roots:
        for path in sorted(root.glob("*.json")) if root.exists() else []:
            payload = read_json(path)
            if not isinstance(payload, dict):
                continue
            url = canonical_url(str(payload.get("source_url") or payload.get("url") or ""))
            if url:
                rows.setdefault(url, {**payload, "_raw_path": str(path)})
    return rows


def frontier_rows(frontier_json: Path) -> List[Dict[str, Any]]:
    payload = read_json(frontier_json)
    rows = payload.get("accepted", []) if isinstance(payload, dict) else []
    return rows if isinstance(rows, list) else []


def assess_esa(*, frontier_json: Path, raw_roots: Sequence[Path], limit: int = 30) -> Dict[str, Any]:
    raws = raw_lookup(raw_roots)
    statuses: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    duplicates = 0
    for row in frontier_rows(frontier_json):
        if len(statuses) >= min(limit, 30):
            break
        url = canonical_url(str(row.get("url") or ""))
        title = normalized_title(str(row.get("title") or ""))
        if (url and url in seen_urls) or (title and title in seen_titles):
            duplicates += 1
            continue
        if url:
            seen_urls.add(url)
        if title:
            seen_titles.add(title)
        raw = raws.get(url)
        if not raw:
            statuses.append({"status": "review_needed", "reason": "raw_missing_preview_only", "url": url, "title": title})
            continue
        quality = quality_fields_for_payload(raw)
        triage = str(quality.get("quality_triage") or "")
        status = "accepted_for_package" if triage == "accepted" else "rejected"
        statuses.append(
            {
                "status": status,
                "reason": "quality_accepted" if status == "accepted_for_package" else f"quality_{triage}",
                "url": url,
                "title": raw.get("title") or title,
                "quality_score": quality.get("quality_score"),
                "quality_triage": triage,
                "quality_reasons": quality.get("quality_reasons", []),
                "raw_path": raw.get("_raw_path", ""),
            }
        )
    counts = Counter(row["status"] for row in statuses)
    return {
        "phase": "Phase 67",
        "mode": "esa_controlled_source_assessment_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_id": SOURCE_ID,
        "selected": len(statuses),
        "accepted_for_package": counts.get("accepted_for_package", 0),
        "review_needed": counts.get("review_needed", 0),
        "rejected": counts.get("rejected", 0),
        "failed": counts.get("failed", 0),
        "duplicates_excluded": duplicates,
        "recommended_next_package_size": counts.get("accepted_for_package", 0),
        "candidate_statuses": statuses,
        "reason_counts": dict(Counter(row.get("reason", "") for row in statuses)),
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
            "# ESA controlled source assessment preview",
            "",
            f"- selected: `{report['selected']}`",
            f"- accepted_for_package: `{report['accepted_for_package']}`",
            f"- review_needed: `{report['review_needed']}`",
            f"- rejected: `{report['rejected']}`",
            f"- failed: `{report['failed']}`",
            f"- recommended_next_package_size: `{report['recommended_next_package_size']}`",
            f"- network_attempted: `{report['network_attempted']}`",
            f"- active_source_unchanged: `{report['active_source_unchanged']}`",
            f"- esa_registry: `{report['registry'].get('esa')}`",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assess ESA controlled preview candidates without formal writes.")
    parser.add_argument("--frontier-json", default=str(ROOT / "evaluation" / "source_frontiers" / "esa_frontier.json"))
    parser.add_argument("--raw-root", action="append", default=[str(ROOT / "data" / "raw_json" / SOURCE_ID)])
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_controlled_assessment_phase67.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "esa_controlled_assessment_phase67.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = assess_esa(frontier_json=Path(args.frontier_json), raw_roots=[Path(p) for p in args.raw_root], limit=args.limit)
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"accepted={report['accepted_for_package']} review={report['review_needed']} rejected={report['rejected']} failed={report['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

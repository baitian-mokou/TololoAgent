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
from scripts.build_nasa_second_shadow_package import combined_package_fingerprints, report_status_fingerprints
from scripts.ingest_manifest_frontier import quality_fields_for_payload
from scripts.select_deduped_frontier_candidates import canonical_url, normalized_title


SOURCE_ID = "nasa"


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
    parts = list(path.resolve().parts)
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1)) or (
        allow_docs and "docs" in parts
    )


def raw_lookup(raw_root: Path) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for path in sorted(raw_root.glob("*.json")) if raw_root.exists() else []:
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        url = canonical_url(str(payload.get("source_url") or payload.get("url") or ""))
        if url:
            rows.setdefault(url, payload)
    return rows


def frontier_candidates(frontier_json: Path) -> List[Dict[str, Any]]:
    payload = read_json(frontier_json)
    return list(payload.get("accepted", [])) if isinstance(payload, dict) and isinstance(payload.get("accepted"), list) else []


def refresh_frontier(
    *,
    frontier_json: Path,
    raw_root: Path,
    exclude_package_dirs: Sequence[Path],
    exclude_report_paths: Sequence[Path],
    target_count: int,
) -> Dict[str, Any]:
    excluded_urls, excluded_titles, excluded_subjects = combined_package_fingerprints(exclude_package_dirs)
    report_urls, report_titles, report_subjects = report_status_fingerprints(exclude_report_paths)
    excluded_urls.update(report_urls)
    excluded_titles.update(report_titles)
    excluded_subjects.update(report_subjects)
    raws = raw_lookup(raw_root)
    accepted: List[Dict[str, Any]] = []
    review_needed: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_count = excluded_count = 0
    for row in frontier_candidates(frontier_json):
        url = canonical_url(str(row.get("url") or ""))
        title = normalized_title(str(row.get("title") or ""))
        if not url:
            rejected.append({"url": "", "reason": "missing_url"})
            continue
        if url in seen:
            duplicate_count += 1
            continue
        seen.add(url)
        if url in excluded_urls or title in excluded_titles or title in excluded_subjects:
            excluded_count += 1
            continue
        raw = raws.get(url)
        if not raw:
            review_needed.append({"url": url, "title": title, "reason": "raw_missing_preview_only"})
            continue
        quality = quality_fields_for_payload(raw)
        triage = quality.get("quality_triage")
        item = {"url": url, "title": raw.get("title") or title, **quality, "reason": "existing_raw_quality"}
        if triage == "accepted":
            accepted.append(item)
        else:
            rejected.append({**item, "reason": f"quality_{triage}"})
        if len(accepted) >= target_count:
            break
    recommended = min(target_count, len(accepted))
    return {
        "phase": "Phase 58",
        "mode": "nasa_frontier_refresh_controlled",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_id": SOURCE_ID,
        "target_count": target_count,
        "frontier_candidates_seen": len(seen),
        "accepted_for_next_preview": len(accepted),
        "review_needed": len(review_needed),
        "rejected": len(rejected),
        "duplicates_excluded": duplicate_count,
        "prior_excluded": excluded_count,
        "recommended_next_package_size": recommended,
        "accepted_candidates": accepted,
        "review_needed_candidates": review_needed[:100],
        "rejected_reason_counts": dict(Counter(item.get("reason", "") for item in rejected)),
        "network_attempted": False,
        "formal_triples_write": False,
        "formal_narratives_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "recommended_next_action": "build_next_package_from_accepted_preview" if accepted else "needs_controlled_live_frontier_refresh_or_manual_seed_review",
    }


def render_md(report: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# NASA frontier refresh candidates",
            "",
            f"- accepted_for_next_preview: `{report['accepted_for_next_preview']}`",
            f"- review_needed: `{report['review_needed']}`",
            f"- rejected: `{report['rejected']}`",
            f"- duplicates_excluded: `{report['duplicates_excluded']}`",
            f"- prior_excluded: `{report['prior_excluded']}`",
            f"- recommended_next_package_size: `{report['recommended_next_package_size']}`",
            f"- network_attempted: `{report['network_attempted']}`",
            f"- active_source_unchanged: `{report['active_source_unchanged']}`",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh NASA frontier candidates without data writes.")
    parser.add_argument("--frontier-json", default=str(ROOT / "evaluation" / "source_frontiers" / "nasa_frontier.json"))
    parser.add_argument("--raw-root", default=str(ROOT / "data" / "raw_json" / SOURCE_ID))
    parser.add_argument("--exclude-package-dir", action="append", default=[])
    parser.add_argument("--exclude-report-json", action="append", default=[])
    parser.add_argument("--target-count", type=int, default=50)
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_frontier_refresh_phase58.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_frontier_refresh_phase58.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = refresh_frontier(
        frontier_json=Path(args.frontier_json),
        raw_root=Path(args.raw_root),
        exclude_package_dirs=[Path(p) for p in args.exclude_package_dir],
        exclude_report_paths=[Path(p) for p in args.exclude_report_json],
        target_count=args.target_count,
    )
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"accepted={report['accepted_for_next_preview']} review={report['review_needed']} rejected={report['rejected']} prior={report['prior_excluded']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.build_nasa_second_shadow_package import report_status_fingerprints
from scripts.ingest_manifest_frontier import fetch_url, payload_for_record, quality_fields_for_payload
from scripts.materialize_manifest_raw_records import safe_name
from scripts.select_deduped_frontier_candidates import canonical_url, normalized_title


SOURCE_ID = "nasa"
ALLOWED_HOSTS = ("science.nasa.gov", "nssdc.gsfc.nasa.gov", "solarsystem.nasa.gov")
Fetcher = Callable[[str, int], Dict[str, str]]


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


def ensure_url(value: str) -> str:
    value = str(value or "").strip()
    if value.startswith(("http://", "https://")):
        return value
    return "https://" + value.lstrip("/")


def allowed_url(url: str) -> bool:
    clean = ensure_url(url).lower()
    return clean.startswith("https://") and any(clean.startswith(f"https://{host}") for host in ALLOWED_HOSTS)


def preview_candidates(phase58: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = phase58.get("review_needed_candidates", [])
    return rows if isinstance(rows, list) else []


def preview_batch(
    *,
    phase58_json: Path,
    out_dir: Path,
    limit: int = 30,
    exclude_report_paths: Sequence[Path] = (),
    fetcher: Fetcher = fetch_url,
) -> Dict[str, Any]:
    if limit > 30:
        limit = 30
    out_dir.mkdir(parents=True, exist_ok=True)
    excluded_urls, excluded_titles, excluded_subjects = report_status_fingerprints(exclude_report_paths)
    selected: List[Dict[str, Any]] = []
    prior_excluded = duplicate_excluded = invalid_excluded = 0
    seen: set[str] = set()
    for candidate in preview_candidates(read_json(phase58_json)):
        url = ensure_url(str(candidate.get("url") or ""))
        url_key = canonical_url(url)
        title_key = normalized_title(str(candidate.get("title") or ""))
        if not allowed_url(url):
            invalid_excluded += 1
            continue
        if url_key in excluded_urls or title_key in excluded_titles or title_key in excluded_subjects:
            prior_excluded += 1
            continue
        if url_key in seen:
            duplicate_excluded += 1
            continue
        seen.add(url_key)
        selected.append({**candidate, "url": url})
        if len(selected) >= limit:
            break

    statuses: List[Dict[str, Any]] = []
    for index, candidate in enumerate(selected, start=1):
        url = candidate["url"]
        try:
            raw = payload_for_record(SOURCE_ID, {"kind": "url", "url": url, "depth": 0, "reason": "phase59_raw_preview"}, fetcher)
            raw.update(quality_fields_for_payload(raw))
            title = str(raw.get("title") or candidate.get("title") or url)
            raw_path = out_dir / "raw_preview_by_item" / f"{index:02d}_{safe_name(title)}.json"
            write_json(raw_path, raw)
            triage = str(raw.get("quality_triage") or "")
            status = "accepted_for_package" if triage == "accepted" else "rejected"
            statuses.append(
                {
                    "status": status,
                    "reason": "quality_accepted" if status == "accepted_for_package" else f"quality_{triage}",
                    "title": title,
                    "url": raw.get("source_url") or raw.get("url") or url,
                    "quality_score": raw.get("quality_score"),
                    "quality_triage": triage,
                    "quality_reasons": raw.get("quality_reasons", []),
                    "raw_preview_path": str(raw_path),
                }
            )
        except Exception as exc:
            statuses.append({"status": "failed", "reason": type(exc).__name__, "url": url, "title": candidate.get("title", "")})

    counts = Counter(row["status"] for row in statuses)
    return {
        "phase": "Phase 59",
        "mode": "nasa_controlled_raw_preview_batch",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_id": SOURCE_ID,
        "limit": limit,
        "selected": len(selected),
        "attempted": len(statuses),
        "accepted_for_package": counts.get("accepted_for_package", 0),
        "rejected": counts.get("rejected", 0),
        "failed": counts.get("failed", 0),
        "prior_excluded": prior_excluded,
        "duplicate_excluded": duplicate_excluded,
        "invalid_excluded": invalid_excluded,
        "candidate_statuses": statuses,
        "rejected_reason_counts": dict(Counter(row.get("reason", "") for row in statuses if row.get("status") == "rejected")),
        "recommended_next_package_size": counts.get("accepted_for_package", 0),
        "out_dir": str(out_dir),
        "network_attempted": bool(statuses),
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
            "# NASA controlled raw preview batch",
            "",
            f"- selected: `{report['selected']}`",
            f"- accepted_for_package: `{report['accepted_for_package']}`",
            f"- rejected: `{report['rejected']}`",
            f"- failed: `{report['failed']}`",
            f"- recommended_next_package_size: `{report['recommended_next_package_size']}`",
            f"- formal_raw_write: `{report['formal_raw_write']}`",
            f"- chroma_write: `{report['chroma_write']}`",
            f"- neo4j_write: `{report['neo4j_write']}`",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview selected NASA raw candidates under evaluation only.")
    parser.add_argument("--phase58-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_frontier_refresh_phase58.json"))
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--exclude-report-json", action="append", default=[])
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_raw_preview_batch_phase59"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_raw_preview_batch_phase59.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_raw_preview_batch_phase59.md"))
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_dir) or not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = preview_batch(
        phase58_json=Path(args.phase58_json),
        out_dir=out_dir,
        limit=args.limit,
        exclude_report_paths=[Path(p) for p in args.exclude_report_json],
    )
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"accepted={report['accepted_for_package']} rejected={report['rejected']} failed={report['failed']} attempted={report['attempted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
from scripts.ingest_manifest_frontier import fetch_url, payload_for_record, quality_fields_for_payload
from scripts.materialize_manifest_raw_records import safe_name
from scripts.select_deduped_frontier_candidates import canonical_url


SOURCE_ID = "esa"
ALLOWED_HOSTS = ("www.esa.int", "esa.int")
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
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return relative.parts[:2] == ("evaluation", "four_source_expansion") or (allow_docs and relative.parts[:1] == ("docs",))


def ensure_url(value: str) -> str:
    value = str(value or "").strip()
    if value.startswith(("http://", "https://")):
        return value
    return "https://" + value.lstrip("/")


def allowed_url(url: str) -> bool:
    clean = ensure_url(url).lower()
    return clean.startswith("https://") and any(clean.startswith(f"https://{host}") for host in ALLOWED_HOSTS)


def phase67_review_needed(phase67: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = phase67.get("candidate_statuses", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if row.get("status") == "review_needed"]


def preview_batch(*, phase67_json: Path, out_dir: Path, limit: int = 16, fetcher: Fetcher = fetch_url) -> Dict[str, Any]:
    limit = min(limit, 16)
    out_dir.mkdir(parents=True, exist_ok=True)
    selected: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    duplicate_excluded = invalid_excluded = 0
    for candidate in phase67_review_needed(read_json(phase67_json)):
        url = ensure_url(str(candidate.get("url") or ""))
        url_key = canonical_url(url)
        if not allowed_url(url):
            invalid_excluded += 1
            continue
        if url_key in seen_urls:
            duplicate_excluded += 1
            continue
        seen_urls.add(url_key)
        selected.append({**candidate, "url": url})
        if len(selected) >= limit:
            break

    statuses: List[Dict[str, Any]] = []
    for index, candidate in enumerate(selected, start=1):
        url = candidate["url"]
        try:
            raw = payload_for_record(SOURCE_ID, {"kind": "url", "url": url, "depth": 0, "reason": "phase68_raw_preview"}, fetcher)
            raw.update(quality_fields_for_payload(raw))
            title = str(raw.get("title") or candidate.get("title") or url)
            raw_path = out_dir / "raw_preview_by_item" / f"{index:02d}_{safe_name(title)}.json"
            write_json(raw_path, raw)
            triage = str(raw.get("quality_triage") or "")
            accepted = triage == "accepted"
            statuses.append(
                {
                    "status": "accepted_for_package" if accepted else "rejected",
                    "reason": "quality_accepted" if accepted else f"quality_{triage or 'unknown'}",
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
        "phase": "Phase 68",
        "mode": "esa_evaluation_only_raw_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_id": SOURCE_ID,
        "limit": limit,
        "selected": len(selected),
        "attempted": len(statuses),
        "accepted_for_package": counts.get("accepted_for_package", 0),
        "rejected": counts.get("rejected", 0),
        "failed": counts.get("failed", 0),
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
            "# ESA evaluation-only raw preview",
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
    parser = argparse.ArgumentParser(description="Preview Phase67 ESA review_needed raw candidates under evaluation only.")
    parser.add_argument("--phase67-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_controlled_assessment_phase67.json"))
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_raw_preview_batch_phase68"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_raw_preview_batch_phase68.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "esa_raw_preview_batch_phase68.md"))
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_dir) or not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = preview_batch(phase67_json=Path(args.phase67_json), out_dir=out_dir, limit=args.limit)
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"accepted={report['accepted_for_package']} rejected={report['rejected']} failed={report['failed']} attempted={report['attempted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

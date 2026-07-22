from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.preview_source_frontier import (
    MANIFEST_DIR,
    classify_item,
    item_record,
    load_manifest_from_path,
    manifest_validation_report,
    quality_context_from_manifest,
    seed_items,
)
from scripts.score_candidate_pages import candidates_from_payload
from src.source_quality.page_quality import score_page


SANDBOX_DIR = ROOT / "evaluation" / "source_quality" / "sandbox"
REGISTERED_SOURCES = {"nasa", "esa", "wikidata"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_sandbox_path(path: Path) -> bool:
    parts = [part.lower() for part in Path(path).parts]
    return any(
        parts[index:index + 3] == ["evaluation", "source_quality", "sandbox"]
        for index in range(len(parts) - 2)
    )


def default_report_path(source_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in source_id).strip("_")
    return SANDBOX_DIR / f"{safe or 'manifest'}_sandbox_report.json"


def candidates_from_manifest(manifest: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    fixture_path = str(manifest.get("fixture_candidates") or "").strip()
    if fixture_path:
        path = Path(fixture_path)
        if not path.is_absolute():
            path = ROOT / path
        return candidates_from_payload(read_json(path), str(manifest.get("source_name") or "generic")), []
    accepted: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in seed_items(manifest):
        ok, reason = classify_item(item, manifest, seen)
        record = item_record(item, reason)
        if ok:
            accepted.append(record)
        else:
            skipped.append(record)
    return accepted, skipped


def snapshot(candidate: Dict[str, Any], result: Dict[str, Any], index: int) -> Dict[str, Any]:
    text = str(candidate.get("text") or "")
    html = str(candidate.get("html") or "")
    return {
        "index": index,
        "url": candidate.get("url") or candidate.get("source_url") or "",
        "title": candidate.get("title") or candidate.get("entity") or candidate.get("qid") or "",
        "text_length": len(text),
        "html_length": len(html),
        "score": result["score"],
        "triage": result["triage"],
        "labels": result["labels"],
        "reasons": result["reasons"][:5],
    }


def build_report(manifest: Dict[str, Any], manifest_path: Path, candidates: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    source_id = str(manifest.get("source_name") or manifest_path.stem)
    validation = manifest_validation_report(manifest, manifest_path)
    quality_context = quality_context_from_manifest(manifest)
    triage_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    items = []
    for index, candidate in enumerate(candidates, start=1):
        scored_candidate = dict(candidate)
        scored_candidate.setdefault("source_name", source_id)
        result = score_page(scored_candidate, quality_context=quality_context)
        triage_counts[result["triage"]] += 1
        reason_counts.update(result.get("reasons", []))
        items.append(snapshot(scored_candidate, result, index))
    return {
        "source_id": source_id,
        "registered": source_id in REGISTERED_SOURCES and manifest_path.parent == MANIFEST_DIR,
        "network": False,
        "mode": "manifest_candidate_sandbox",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path),
        "fixture_candidates_path": manifest.get("fixture_candidates", ""),
        "manifest_validation": validation,
        "candidate_count": len(items),
        "triage_counts": dict(sorted(triage_counts.items())),
        "top_reasons": dict(reason_counts.most_common(10)),
        "safety_flags": {
            "formal_pipeline_write": False,
            "raw_json_write": False,
            "triples_write": False,
            "chroma_write": False,
            "neo4j_write": False,
            "network_disabled": True,
            "unregistered_ingest_blocked": source_id not in REGISTERED_SOURCES,
        },
        "selected_candidate_snapshots": items[:20],
    }


def print_summary(report: Dict[str, Any]) -> None:
    print(
        f"{report['source_id']}: sandbox candidates={report['candidate_count']} "
        f"registered={report['registered']} network={report['network']} "
        f"triage={report['triage_counts']}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build a no-network, no-formal-write sandbox report for a Manifest 2.0 candidate source.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--input-json", default="", help="Optional local candidate JSON/list/frontier/raw file.")
    parser.add_argument("--report-json", default="")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    manifest = load_manifest_from_path(manifest_path)
    validation = manifest_validation_report(manifest, manifest_path)
    if not validation["passed"]:
        print(f"manifest validation failed: {validation['errors']}", file=sys.stderr)
        return 2

    source_id = str(manifest.get("source_name") or manifest_path.stem)
    report_path = Path(args.report_json) if args.report_json else default_report_path(source_id)
    if not is_sandbox_path(report_path):
        print("report-json must be under evaluation/source_quality/sandbox", file=sys.stderr)
        return 2

    if args.input_json:
        candidates = candidates_from_payload(read_json(Path(args.input_json)), source_id)
        skipped: List[Dict[str, Any]] = []
    else:
        candidates, skipped = candidates_from_manifest(manifest)
    report = build_report(manifest, manifest_path, candidates)
    report["frontier_skipped_count"] = len(skipped)
    report["frontier_skipped"] = skipped[:20]
    report["safety_flags"]["sandbox_report_only"] = True
    write_json(report_path, report)
    print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.build_nasa_limited_shadow_package import approval_payload, formal_shadow_plan, render_review_sample
from scripts.build_nasa_second_shadow_package import (
    build_package_files,
    combined_package_fingerprints,
    report_status_fingerprints,
    sample_items,
)
from scripts.ingest_manifest_frontier import quality_fields_for_payload
from scripts.materialize_manifest_raw_records import convert_raw_payload
from scripts.preview_nasa_text_relation_extraction import extract_text_relations, normalize_title, validate_triples
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


def accepted_phase59_items(phase59_json: Path) -> List[Dict[str, Any]]:
    report = read_json(phase59_json)
    rows = report.get("candidate_statuses", []) if isinstance(report, dict) else []
    return [row for row in rows if row.get("status") == "accepted_for_package"]


def overlaps_prior(raw: Dict[str, Any], triples: Sequence[Dict[str, Any]], urls: set[str], titles: set[str], subjects: set[str]) -> bool:
    url = canonical_url(str(raw.get("source_url") or raw.get("url") or ""))
    title = normalized_title(str(raw.get("title") or ""))
    if url in urls or title in titles or title in subjects:
        return True
    for triple in triples:
        subject = normalized_title(str(triple.get("subject") or ""))
        if subject and subject in subjects:
            return True
    return False


def item_from_raw(raw_path: Path, status: Dict[str, Any]) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
    raw = read_json(raw_path)
    if not isinstance(raw, dict) or not raw:
        return None, {"status": "failed", "reason": "raw_preview_missing", "url": status.get("url", "")}
    raw.update(quality_fields_for_payload(raw))
    title = str(raw.get("title") or status.get("title") or status.get("url") or "NASA item")
    url = str(raw.get("source_url") or raw.get("url") or status.get("url") or "")
    if raw.get("quality_triage") != "accepted":
        return None, {"status": "rejected", "reason": f"quality_{raw.get('quality_triage')}", "title": title, "url": url}
    converted = convert_raw_payload(SOURCE_ID, raw)
    trial = {
        "source_id": SOURCE_ID,
        "title": title,
        "source_url": url,
        "narratives": converted.get("narratives", []),
        "raw_path": str(raw_path),
    }
    triples_raw, narrative_count = extract_text_relations(trial)
    triples, warnings = validate_triples(triples_raw, url)
    if not triples or not trial["narratives"]:
        return None, {"status": "rejected", "reason": "missing_triples_or_narratives", "title": title, "url": url}
    return {
        "source_id": SOURCE_ID,
        "title": normalize_title(title),
        "source_url": url,
        "raw_preview_path": str(raw_path),
        "triples": triples,
        "narratives": trial["narratives"],
        "warnings": warnings,
        "narratives_used": narrative_count,
    }, {"status": "packaged", "title": title, "url": url}


def build_fourth_package(
    *,
    phase59_json: Path,
    exclude_package_dirs: Sequence[Path],
    exclude_report_paths: Sequence[Path],
    out_dir: Path,
    approval_template: Path,
) -> Dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    urls, titles, subjects = combined_package_fingerprints(exclude_package_dirs)
    report_urls, report_titles, report_subjects = report_status_fingerprints(exclude_report_paths)
    urls.update(report_urls)
    titles.update(report_titles)
    subjects.update(report_subjects)
    packaged: List[Dict[str, Any]] = []
    statuses: List[Dict[str, Any]] = []
    prior_excluded = 0
    for status in accepted_phase59_items(phase59_json):
        raw_path = Path(str(status.get("raw_preview_path") or ""))
        item, item_status = item_from_raw(raw_path, status)
        if item and overlaps_prior(read_json(raw_path), item.get("triples", []), urls, titles, subjects):
            prior_excluded += 1
            statuses.append({"status": "duplicate_skipped", "reason": "prior_url_title_subject_overlap", "title": item.get("title"), "url": item.get("source_url")})
            continue
        statuses.append(item_status)
        if item:
            packaged.append(item)
    triples, narratives = build_package_files(out_dir, packaged)
    samples = sample_items(packaged)
    write_json(out_dir / "review_sample.json", samples)
    write_text(out_dir / "review_sample.md", render_review_sample(samples))
    write_json(approval_template, approval_payload(len(packaged)))
    manifest = {
        "package": "nasa_fourth_shadow_package_phase60",
        "source_id": SOURCE_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": len(packaged),
        "triples": len(triples),
        "narratives": len(narratives),
        "approval_status": "pending",
        "formal_write": False,
    }
    write_json(out_dir / "package_manifest.json", manifest)
    rejected = sum(1 for row in statuses if row.get("status") == "rejected")
    failed = sum(1 for row in statuses if row.get("status") == "failed")
    relation_counts = Counter(row.get("predicate", "") for row in triples)
    return {
        "phase": "Phase 60",
        "mode": "nasa_fourth_shadow_package_preparation",
        "generated_at": manifest["generated_at"],
        "source_id": SOURCE_ID,
        "selected_count": len(accepted_phase59_items(phase59_json)),
        "packaged_items": len(packaged),
        "rejected": rejected,
        "failed": failed,
        "prior_excluded": prior_excluded,
        "triples": len(triples),
        "narratives": len(narratives),
        "relations_count": dict(sorted(relation_counts.items())),
        "candidate_statuses": statuses,
        "sample_items": samples,
        "approval_status": "pending",
        "approval_template": str(approval_template),
        "out_dir": str(out_dir),
        "formal_shadow_write_plan": formal_shadow_plan(len(packaged), len(triples), len(narratives)),
        "network_attempted": False,
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
            "# NASA fourth shadow package preparation",
            "",
            f"- selected_count: `{report['selected_count']}`",
            f"- packaged_items: `{report['packaged_items']}`",
            f"- rejected: `{report['rejected']}`",
            f"- failed: `{report['failed']}`",
            f"- prior_excluded: `{report['prior_excluded']}`",
            f"- triples: `{report['triples']}`",
            f"- narratives: `{report['narratives']}`",
            f"- approval_status: `{report['approval_status']}`",
            f"- chroma_write: `{report['chroma_write']}`",
            f"- neo4j_write: `{report['neo4j_write']}`",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NASA fourth shadow package from Phase59 accepted raw preview.")
    parser.add_argument("--phase59-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_raw_preview_batch_phase59.json"))
    parser.add_argument("--exclude-package-dir", action="append", default=[])
    parser.add_argument("--exclude-report-json", action="append", default=[])
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_fourth_shadow_package_phase60"))
    parser.add_argument("--report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_fourth_shadow_package_phase60.json"))
    parser.add_argument("--report-md", default=str(ROOT / "docs" / "nasa_fourth_shadow_package_phase60.md"))
    parser.add_argument("--approval-template", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_fourth_shadow_package_approval_phase60.json"))
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir)
    report_json = Path(args.report_json)
    report_md = Path(args.report_md)
    approval = Path(args.approval_template)
    if not output_allowed(out_dir) or not output_allowed(report_json) or not output_allowed(report_md, allow_docs=True) or not output_allowed(approval):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = build_fourth_package(
        phase59_json=Path(args.phase59_json),
        exclude_package_dirs=[Path(p) for p in args.exclude_package_dir],
        exclude_report_paths=[Path(p) for p in args.exclude_report_json],
        out_dir=out_dir,
        approval_template=approval,
    )
    write_json(report_json, report)
    write_text(report_md, render_md(report))
    print(f"packaged={report['packaged_items']} rejected={report['rejected']} failed={report['failed']} triples={report['triples']} narratives={report['narratives']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

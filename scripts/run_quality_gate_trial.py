from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ingest_manifest_frontier import ingest_frontier
from scripts.preview_source_frontier import build_frontier_preview, load_manifest


OUT_DIR = ROOT / "evaluation" / "source_quality"
REPORT_PATH = OUT_DIR / "quality_gate_phase13_report.json"
ALLOWED_SOURCES = ("nasa", "esa")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_sources(sources: Iterable[str]) -> List[str]:
    selected = [str(source).strip().lower() for source in sources if str(source).strip()]
    disallowed = [source for source in selected if source not in ALLOWED_SOURCES]
    if disallowed:
        raise ValueError("Phase 13 quality gate trial only enables skip-rejected for nasa/esa; wikidata stays raw-stage only.")
    return selected or list(ALLOWED_SOURCES)


def compact_sample(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "status": item.get("status", ""),
        "reason": item.get("reason", ""),
        "score": item.get("quality_score", 0),
        "triage": item.get("quality_triage", ""),
        "labels": item.get("quality_labels", []),
        "reasons": item.get("quality_reasons", []),
        "text_length": item.get("text_length", 0),
    }


def samples_by_triage(report: Dict[str, Any], triage: str, limit: int) -> List[Dict[str, Any]]:
    samples = []
    for item in report.get("items", []):
        if item.get("quality_triage") == triage:
            samples.append(compact_sample(item))
        if len(samples) >= limit:
            break
    return samples


def skipped_quality_rejected(report: Dict[str, Any]) -> int:
    return sum(1 for item in report.get("items", []) if item.get("reason") == "skipped_quality_rejected")


def false_kill_risk(rejected_samples: Sequence[Dict[str, Any]]) -> tuple[str, str]:
    if not rejected_samples:
        return "low", "no rejected samples in the trial"
    suspicious = [
        item for item in rejected_samples
        if int(item.get("score", 0) or 0) >= 45
        or any(label in set(item.get("labels", [])) for label in ("fact_page", "mission_page", "has_table"))
    ]
    if suspicious:
        return "medium", "some rejected pages still have fact/mission/table or mid-score signals; review before default skip"
    return "low", "rejected pages show low-value signals such as media/search/short text"


def report_counts(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "fetched": int(report.get("fetched_count", 0) or 0),
        "skipped": int(report.get("skipped_count", 0) or 0),
        "skipped_quality_rejected": skipped_quality_rejected(report),
        "failed": int(report.get("failed_count", 0) or 0),
        "triage_counts": report.get("quality_summary", {}).get("triage_counts", {}),
    }


def compare_source_reports(source: str, baseline: Dict[str, Any], gated: Dict[str, Any], trial_label: str = "phase13") -> Dict[str, Any]:
    rejected = samples_by_triage(baseline, "rejected", 10)
    accepted = samples_by_triage(baseline, "accepted", 5)
    review_needed = samples_by_triage(baseline, "review_needed", 5)
    exploratory = samples_by_triage(baseline, "exploratory", 5)
    risk, reason = false_kill_risk(rejected)
    recommend = risk == "low" and int(gated.get("failed_count", 0) or 0) <= int(baseline.get("failed_count", 0) or 0)
    return {
        "source": source,
        "baseline": report_counts(baseline),
        "gated": report_counts(gated),
        "rejected_samples": rejected,
        "accepted_samples": accepted,
        "review_needed_samples": review_needed,
        "exploratory_samples": exploratory,
        "false_kill_risk": risk,
        "false_kill_risk_reason": reason,
        "recommend_skip_rejected_for_small_batch": recommend,
        "recommendation": (
            "Use --quality-report --skip-rejected for explicit small-batch nasa/esa ingestion templates; inspect rejected_samples after each batch."
            if recommend
            else "Keep --skip-rejected experimental; inspect rejected_samples before using it in small-batch templates."
        ),
        "raw_overwrite_note": f"trial raw is written under evaluation/source_quality/{trial_label}_raw; same title/url may overwrite only prior trial files, not formal data/raw_json",
    }


def run_source_trial(source: str, frontier_limit: int, ingest_limit: int, trial_label: str = "phase13") -> Dict[str, Any]:
    manifest = load_manifest(source)
    frontier = build_frontier_preview(manifest, frontier_limit, fetch_links=True, quality_score=True)
    frontier_path = OUT_DIR / f"{source}_quality_frontier_{trial_label}.json"
    write_json(frontier_path, frontier)

    baseline = ingest_frontier(
        source_name=source,
        manifest=manifest,
        frontier=frontier,
        limit=ingest_limit,
        delay=float(manifest.get("crawl_delay", 0) or 0),
        raw_root=OUT_DIR / f"{trial_label}_raw" / "baseline",
        report_path=OUT_DIR / f"{source}_quality_baseline_{trial_label}.json",
        quality_report=True,
    )
    gated = ingest_frontier(
        source_name=source,
        manifest=manifest,
        frontier=frontier,
        limit=ingest_limit,
        delay=float(manifest.get("crawl_delay", 0) or 0),
        raw_root=OUT_DIR / f"{trial_label}_raw" / "gated",
        report_path=OUT_DIR / f"{source}_quality_gated_{trial_label}.json",
        quality_report=True,
        skip_rejected=True,
    )
    summary = compare_source_reports(source, baseline, gated, trial_label=trial_label)
    summary["frontier"] = {
        "path": str(frontier_path),
        "accepted": frontier.get("accepted_count", 0),
        "skipped": frontier.get("skipped_count", 0),
        "quality_summary": frontier.get("quality_summary", {}),
    }
    return summary


def build_phase13_report(sources: Sequence[str], frontier_limit: int, ingest_limit: int, trial_label: str = "phase13") -> Dict[str, Any]:
    selected_sources = validate_sources(sources)
    results = {
        source: run_source_trial(source, frontier_limit, ingest_limit, trial_label=trial_label)
        for source in selected_sources
    }
    return {
        "mode": f"{trial_label}_quality_gate_trial",
        "generated_at": utc_now(),
        "frontier_limit": int(frontier_limit),
        "ingest_limit": int(ingest_limit),
        "sources": results,
        "wikidata_note": "Wikidata is intentionally excluded from skip-rejected trial; use EntityData/raw-stage scoring instead of metadata-only web scoring.",
    }


def print_summary(report: Dict[str, Any]) -> None:
    print("source | baseline fetched/skipped/failed | gated fetched/skipped_quality_rejected/failed | risk")
    print("--- | --- | --- | ---")
    for source, item in report["sources"].items():
        baseline = item["baseline"]
        gated = item["gated"]
        print(
            f"{source} | {baseline['fetched']}/{baseline['skipped']}/{baseline['failed']} | "
            f"{gated['fetched']}/{gated['skipped_quality_rejected']}/{gated['failed']} | "
            f"{item['false_kill_risk']}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run a small NASA/ESA quality gate baseline-vs-gated trial.")
    parser.add_argument("--sources", nargs="*", default=list(ALLOWED_SOURCES), help="Allowed: nasa esa. Wikidata is guarded off.")
    parser.add_argument("--frontier-limit", type=int, default=40)
    parser.add_argument("--ingest-limit", type=int, default=30)
    parser.add_argument("--trial-label", default="phase13")
    parser.add_argument("--report-json", default=str(REPORT_PATH))
    args = parser.parse_args(argv)

    report = build_phase13_report(args.sources, args.frontier_limit, args.ingest_limit, trial_label=args.trial_label)
    write_json(Path(args.report_json), report)
    print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

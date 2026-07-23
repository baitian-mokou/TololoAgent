import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase112"
DOC_PATH = ROOT / "docs" / "four_source_filtered_review_closure_phase112.md"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def is_noise(text: str) -> bool:
    stripped = (text or "").strip()
    lower = stripped.lower()
    if not stripped:
        return True
    if lower.startswith("<!doctype") or "<html" in lower or "<script" in lower:
        return True
    if (stripped.startswith("{") and ('"source"' in lower or '"source_url"' in lower or '"narrative_excerpt"' in lower)):
        return True
    if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
        return True
    boilerplate_hits = sum(token in lower for token in ("latest", "news", "index", "listing", "menu", "footer", "navigation"))
    return boilerplate_hits >= 3


def _thin_coherent(row: dict) -> bool:
    return (
        row.get("evidence_class") == "thin"
        and row.get("source") == "wikidata"
        and bool(row.get("source_url_or_entity"))
        and bool(row.get("provenance", {}).get("phase110_url_or_entity"))
        and "thin_evidence_requires_review" in row.get("risk_labels", [])
    )


def _empty_or_meaningless_triples(row: dict) -> bool:
    triples = row.get("triples_preview") or []
    if not triples:
        return True
    for triple in triples:
        if not triple.get("subject") or not triple.get("predicate") or not triple.get("object"):
            return True
    return False


def verdict_for(row: dict) -> tuple[str, str]:
    required_missing = not row.get("source") or not row.get("source_url_or_entity") or not row.get("provenance")
    if required_missing:
        return "REJECT_FOR_REVIEW", "missing_metadata_or_provenance"
    if _thin_coherent(row):
        return "ACCEPT_WITH_CONDITIONS", "thin_qid_source_fact_coherent"
    if is_noise(row.get("narrative", "")):
        return "REJECT_FOR_REVIEW", "html_json_or_boilerplate_noise"
    if _empty_or_meaningless_triples(row):
        return "REJECT_FOR_REVIEW", "empty_or_meaningless_triple"
    return "ACCEPT_WITH_CONDITIONS", "accepted_with_conditions_pending_review"


def _with_verdict(row: dict) -> dict:
    verdict, reason = verdict_for(row)
    result = dict(row)
    result["review_status"] = verdict
    result["reviewer_reason"] = reason
    result["production_ready"] = False
    result["apply_preflight_allowed"] = False
    return result


def build_filtered_review(phase111_report: Path) -> dict:
    phase111 = _load(phase111_report)
    reviewed = [_with_verdict(row) for row in phase111["normalized_records"]]
    filtered = [row for row in reviewed if row["review_status"] == "ACCEPT_WITH_CONDITIONS"]
    rejected = [row for row in reviewed if row["review_status"] == "REJECT_FOR_REVIEW"]
    overall = "DEEPER_CRAWL_REVIEW_QUEUE_GO_WITH_CONDITIONS" if filtered else "DEEPER_CRAWL_REVIEW_QUEUE_NO_GO"
    return {
        "phase": "Phase112",
        "mode": "deeper_crawl_filtered_review_verdict_closure",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_report": str(phase111_report.relative_to(ROOT)),
        "input_count": len(reviewed),
        "filtered_count": len(filtered),
        "rejected_count": len(rejected),
        "filtered_counts_by_source": dict(Counter(row["source"] for row in filtered)),
        "rejected_counts_by_source": dict(Counter(row["source"] for row in rejected)),
        "reject_reasons": dict(Counter(row["reviewer_reason"] for row in rejected)),
        "filtered_queue": filtered,
        "rejected_queue": rejected,
        "overall_verdict": overall,
        "risk_labels": [
            "Filtered queue is conditional only.",
            "HTML/JSON/listing noise rejected.",
            "Thin Wikidata facts require reviewer confirmation.",
        ],
        "next_recommendation": "review filtered conditional queue; no apply/preflight",
        "production_ready": False,
        "preflight_allowed": False,
        "apply_preflight_allowed": False,
        "apply_approved": False,
        "ingest_approved": False,
        "preflight_approved": False,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": "zh_wikipedia",
        "active_source_unchanged": True,
        "clear_source_ingestion_outputs_called": False,
    }


def _markdown(report: dict) -> str:
    lines = [
        "# Phase112 Filtered Review Verdict Closure",
        "",
        f"- overall_verdict: {report['overall_verdict']}",
        f"- input_count: {report['input_count']}",
        f"- filtered_count: {report['filtered_count']} {report['filtered_counts_by_source']}",
        f"- rejected_count: {report['rejected_count']} {report['rejected_counts_by_source']}",
        f"- reject_reasons: {report['reject_reasons']}",
        "- production/preflight/apply/ingest: false",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict) -> list[Path]:
    paths = [
        PHASE_DIR / "filtered_review_verdict_phase112.json",
        PHASE_DIR / "filtered_review_verdict_phase112.md",
        PHASE_DIR / "filtered_queue_phase112.json",
        PHASE_DIR / "rejected_queue_phase112.json",
        DOC_PATH,
    ]
    for path in paths:
        if not output_allowed(path, allow_docs=path == DOC_PATH):
            raise ValueError(f"blocked output path: {path}")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    (PHASE_DIR / "filtered_review_verdict_phase112.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "filtered_review_verdict_phase112.md").write_text(_markdown(report), encoding="utf-8")
    (PHASE_DIR / "filtered_queue_phase112.json").write_text(json.dumps(report["filtered_queue"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "rejected_queue_phase112.json").write_text(json.dumps(report["rejected_queue"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DOC_PATH.write_text(_markdown(report), encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase112 filtered review verdict closure.")
    parser.add_argument("--phase111-report", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase111" / "normalize_review_preview_phase111.json")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_filtered_review(args.phase111_report)
    if args.write:
        write_outputs(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

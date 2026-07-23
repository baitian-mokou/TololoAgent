import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase111"
DOC_PATH = ROOT / "docs" / "four_source_normalize_review_phase111.md"
SCHEMA_VERSION = "phase111.normalize_review.v1"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _narrative(row: dict) -> str:
    text = _clean(row.get("text_excerpt", ""))
    title = row["title_or_id"]
    if row["quality_status"] == "thin":
        return f"{title} has thin source evidence and requires reviewer confirmation."
    return text[:500] or f"{title} has accepted preview evidence from {row['url_or_entity']}."


def _triples(row: dict, narrative: str) -> list[dict]:
    if row["quality_status"] == "thin":
        return [
            {"subject": row["title_or_id"], "predicate": "HAS_SOURCE_ENTITY", "object": row["url_or_entity"]},
        ]
    return [
        {"subject": row["title_or_id"], "predicate": "SOURCE_URL", "object": row["url_or_entity"]},
        {"subject": row["title_or_id"], "predicate": "HAS_REVIEW_TEXT", "object": narrative[:220]},
    ]


def normalize_record(row: dict) -> dict:
    evidence = row["quality_status"]
    narrative = _narrative(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": row["source"],
        "title_or_id": row["title_or_id"],
        "source_url_or_entity": row["url_or_entity"],
        "extraction_method": row["method"],
        "evidence_class": evidence,
        "narrative": narrative,
        "triples_preview": _triples(row, narrative),
        "provenance": {
            "input_phase": "Phase110",
            "phase110_url_or_entity": row["url_or_entity"],
            "phase110_fetch_status": row.get("fetch_status"),
            "phase110_status_code": row.get("status_code"),
        },
        "quality_flags": row.get("quality_flags", []),
        "risk_labels": ["thin_evidence_requires_review"] if evidence == "thin" else [],
        "review_status": "conditional_review" if evidence == "thin" else "pending_review",
        "production_ready": False,
        "apply_preflight_allowed": False,
    }


def build_normalize_review(phase110_report: Path) -> dict:
    phase110 = _load(phase110_report)
    included = [row for row in phase110["preview_records"] if row["quality_status"] in {"accepted", "thin"}]
    records = [normalize_record(row) for row in included]
    seen: set[tuple[str, str]] = set()
    deduped = []
    for row in records:
        key = (row["source"], row["source_url_or_entity"])
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    source_counts = dict(Counter(row["source"] for row in deduped))
    return {
        "phase": "Phase111",
        "mode": "deeper_crawl_normalize_review_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_report": str(phase110_report.relative_to(ROOT)),
        "normalized_count": len(deduped),
        "conditional_count": sum(1 for row in deduped if row["evidence_class"] == "thin"),
        "rejected_excluded": sum(1 for row in phase110["preview_records"] if row["quality_status"] == "rejected"),
        "source_breakdown": source_counts,
        "normalized_records": deduped,
        "quality_status": "normalize_review_preview_ready_with_thin_risks",
        "risks": [
            "Thin Wikidata records are conditional_review only.",
            "Accepted preview records still require review thread quality verdict.",
            "Rejected Phase110 records are excluded from Phase111.",
        ],
        "next_recommendation": "review thread quality verdict; no apply/preflight",
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
        "# Phase111 Normalize Review Preview",
        "",
        f"- normalized_count: {report['normalized_count']}",
        f"- conditional_count: {report['conditional_count']}",
        f"- rejected_excluded: {report['rejected_excluded']}",
        f"- source_breakdown: {report['source_breakdown']}",
        f"- quality_status: {report['quality_status']}",
        "- production/preflight/apply/ingest: false",
        "",
        "## Risks",
    ]
    lines += [f"- {risk}" for risk in report["risks"]]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict) -> list[Path]:
    paths = [
        PHASE_DIR / "normalize_review_preview_phase111.json",
        PHASE_DIR / "normalize_review_preview_phase111.md",
        DOC_PATH,
    ]
    for path in paths:
        if not output_allowed(path, allow_docs=path == DOC_PATH):
            raise ValueError(f"blocked output path: {path}")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    (PHASE_DIR / "normalize_review_preview_phase111.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "normalize_review_preview_phase111.md").write_text(_markdown(report), encoding="utf-8")
    DOC_PATH.write_text(_markdown(report), encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase111 normalize review preview.")
    parser.add_argument("--phase110-report", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase110" / "controlled_deeper_crawl_preview_phase110.json")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_normalize_review(args.phase110_report)
    if args.write:
        write_outputs(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

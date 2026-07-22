from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


REQUIRED_SOURCES = ("zh_wikipedia", "nasa", "esa", "wikidata")
REVIEW_STATUS = "pending_manual_or_reviewer_check"


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
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase93") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def sample_to_review_row(row: Dict[str, Any]) -> Dict[str, Any]:
    narrative = row.get("narrative", {}) if isinstance(row.get("narrative"), dict) else {}
    metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
    provenance = row.get("provenance", {}) if isinstance(row.get("provenance"), dict) else {}
    triples = row.get("triples", []) if isinstance(row.get("triples"), list) else []
    return {
        "source": row.get("source", ""),
        "title": row.get("title", ""),
        "source_url": row.get("source_url", ""),
        "source_id": row.get("source", ""),
        "narrative_excerpt": str(narrative.get("text", ""))[:500],
        "triples": triples[:2],
        "provenance": provenance,
        "quality_flags": metadata.get("quality_flags", {}),
        "schema_version": metadata.get("schema_version", ""),
        "review_status": REVIEW_STATUS,
        "review_questions": [
            "Is the narrative factually relevant to the title/source?",
            "Are provenance and source metadata trustworthy enough for shadow review?",
            "Are the preview triples meaningful and non-noisy?",
            "For NASA repaired metadata, is the Phase86 repair evidence acceptable?",
        ],
    }


def build_review_package(*, expanded_sample_report: Path, closure_report: Path) -> Dict[str, Any]:
    phase91 = read_json(expanded_sample_report)
    phase92 = read_json(closure_report)
    raw_samples = phase91.get("samples", {}) if isinstance(phase91.get("samples"), dict) else {}
    samples_by_source: Dict[str, List[Dict[str, Any]]] = {}
    for source in REQUIRED_SOURCES:
        rows = raw_samples.get(source, []) if isinstance(raw_samples.get(source), list) else []
        samples_by_source[source] = [sample_to_review_row(row) for row in rows]
    sample_counts = {source: len(rows) for source, rows in samples_by_source.items()}
    registry = {s: SOURCE_REGISTRY.get(s, "unknown") for s in REQUIRED_SOURCES}
    return {
        "phase": "Phase 93",
        "mode": "sample_quality_review_package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_status": REVIEW_STATUS,
        "samples_by_source": samples_by_source,
        "sample_counts": sample_counts,
        "total_samples": sum(sample_counts.values()),
        "production_ready": False,
        "apply_approved": False,
        "ingest_approved": False,
        "closure_verdict": phase92.get("closure_verdict", "sample_review_ready_approval_pending"),
        "remaining_risks": phase92.get("remaining_risks", []),
        "next_recommendation": "send to review thread for content-quality verdict",
        "package_files": [
            "review_sample.json",
            "review_sample.md",
            "review_checklist.md",
            "four_source_sample_quality_review_package_phase93.json",
        ],
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": registry,
    }


def render_review_sample(package: Dict[str, Any]) -> str:
    lines = ["# Four-source Review Sample", "", f"Review status: `{REVIEW_STATUS}`", ""]
    for source in REQUIRED_SOURCES:
        lines.extend([f"## {source}", ""])
        for idx, row in enumerate(package.get("samples_by_source", {}).get(source, []), 1):
            triples = row.get("triples", [])
            lines.extend(
                [
                    f"### {idx}. {row.get('title', '')}",
                    f"- source_url: `{row.get('source_url', '')}`",
                    f"- source_id: `{row.get('source_id', '')}`",
                    f"- review_status: `{row.get('review_status', REVIEW_STATUS)}`",
                    f"- narrative: {row.get('narrative_excerpt', '')}",
                    f"- provenance: `{json.dumps(row.get('provenance', {}), ensure_ascii=False)}`",
                    f"- quality_flags: `{json.dumps(row.get('quality_flags', {}), ensure_ascii=False)}`",
                    "- triples:",
                ]
            )
            for triple in triples:
                lines.append(f"  - `{triple.get('subject', '')}` `{triple.get('predicate', '')}` `{triple.get('object', '')}`")
            lines.extend(["- review questions:", "  - factual relevance?", "  - metadata trustworthy?", "  - triples meaningful?", ""])
    return "\n".join(lines)


def render_review_checklist(package: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Review Checklist",
            "",
            f"- review_status: `{REVIEW_STATUS}`",
            "- Check factual relevance against title/source URL.",
            "- Check metadata/provenance credibility.",
            "- Check whether triples are meaningful and non-noisy.",
            "- For NASA, check whether metadata repair evidence is acceptable.",
            "- Mark noise, ambiguity, or source mismatch for follow-up.",
            "- This package is not an apply or ingest authorization.",
            "",
        ]
    )


def render_report(package: Dict[str, Any]) -> str:
    lines = [
        "# Phase93 Sample Quality Review Package",
        "",
        f"- total_samples: `{package['total_samples']}`",
        f"- production flag: `{package['production_ready']}`",
        f"- review_status: `{REVIEW_STATUS}`",
        "",
        "| source | samples |",
        "|---|---:|",
    ]
    for source in REQUIRED_SOURCES:
        lines.append(f"| {source} | {int(package['sample_counts'].get(source, 0))} |")
    lines.extend(["", "Next: send to review thread for content-quality verdict.", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Phase93 reviewer-facing sample quality package.")
    parser.add_argument("--expanded-sample-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase91" / "four_source_expanded_review_sample_gate_phase91.json"))
    parser.add_argument("--closure-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase92" / "four_source_review_sample_closure_phase92.json"))
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase93"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_sample_quality_review_package_phase93.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_md = Path(args.out_md)
    if not output_allowed(out_dir / "review_sample.json") or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase93 or docs/", file=sys.stderr)
        return 2
    package = build_review_package(expanded_sample_report=Path(args.expanded_sample_report), closure_report=Path(args.closure_report))
    write_json(out_dir / "review_sample.json", package)
    write_text(out_dir / "review_sample.md", render_review_sample(package))
    write_text(out_dir / "review_checklist.md", render_review_checklist(package))
    write_json(out_dir / "four_source_sample_quality_review_package_phase93.json", package)
    write_text(out_md, render_report(package))
    print(f"samples={package['total_samples']} review_status={package['review_status']} production={package['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

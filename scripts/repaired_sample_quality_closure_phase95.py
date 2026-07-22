from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


REQUIRED_SOURCES = ("zh_wikipedia", "nasa", "esa", "wikidata")


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase95") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def build_closure(*, phase94_report: Path, phase93_report: Path, phase92_report: Path) -> Dict[str, Any]:
    phase94 = read_json(phase94_report)
    phase93 = read_json(phase93_report)
    phase92 = read_json(phase92_report)
    counts = phase94.get("counts_by_source", {}) if isinstance(phase94.get("counts_by_source"), dict) else {}
    source_verdicts = {
        "esa": "reviewable_candidate",
        "zh_wikipedia": "reviewable_with_template_noise",
        "wikidata": "reviewable_thin_facts_needs_enrichment",
        "nasa": "no_go_current_samples_rejected"
        if counts.get("nasa", {}).get("rejected") == counts.get("nasa", {}).get("total")
        else "needs_manual_quality_review",
    }
    nasa_blocks = source_verdicts["nasa"] == "no_go_current_samples_rejected"
    return {
        "phase": "Phase 95",
        "mode": "repaired_sample_quality_verdict_closure",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_reports": {
            "phase94": str(phase94_report.relative_to(ROOT)),
            "phase93": str(phase93_report.relative_to(ROOT)),
            "phase92": str(phase92_report.relative_to(ROOT)),
        },
        "phase93_total_samples": phase93.get("total_samples"),
        "phase92_verdict": phase92.get("closure_verdict") or phase92.get("verdict"),
        "counts_by_source": counts,
        "source_verdicts": source_verdicts,
        "overall_verdict": "partial_source_review_ready_nasa_blocked"
        if nasa_blocks
        else "partial_source_review_ready_pending_manual_check",
        "shadow_apply_preflight_recommended": False,
        "production_ready": False,
        "apply_approved": False,
        "ingest_approved": False,
        "recommended_next": [
            "Re-sample NASA or improve existing-text extraction before any preflight.",
            "Enrich Wikidata beyond thin entity identifiers before richer narrative review.",
            "Send ESA and zh_wikipedia samples to manual/reviewer quality review.",
        ],
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in REQUIRED_SOURCES},
    }


def render_report(report: Dict[str, Any]) -> str:
    lines = [
        "# Phase95 Repaired Sample Quality Verdict Closure",
        "",
        f"- overall_verdict: `{report['overall_verdict']}`",
        f"- production_ready: `{report['production_ready']}`",
        f"- shadow_apply_preflight_recommended: `{report['shadow_apply_preflight_recommended']}`",
        "",
        "| source | total | repaired | preserved | rejected | verdict |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for source in REQUIRED_SOURCES:
        c = report["counts_by_source"].get(source, {})
        lines.append(
            f"| {source} | {c.get('total', 0)} | {c.get('repaired', 0)} | "
            f"{c.get('preserved', 0)} | {c.get('rejected', 0)} | `{report['source_verdicts'][source]}` |"
        )
    lines.extend(
        [
            "",
            "Next recommendations:",
            "- NASA needs re-sampling or stronger existing-text extraction before preflight.",
            "- Wikidata is reviewable as thin entity facts, not rich narrative.",
            "- ESA and zh_wikipedia can proceed to manual/reviewer quality review.",
            "",
            "No apply, ingest, Chroma, Neo4j, default raw, or default triples writes are authorized.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Phase95 repaired sample quality closure.")
    parser.add_argument(
        "--phase94-report",
        default=str(
            ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase94"
            / "four_source_sample_content_quality_repair_phase94.json"
        ),
    )
    parser.add_argument(
        "--phase93-report",
        default=str(
            ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase93"
            / "four_source_sample_quality_review_package_phase93.json"
        ),
    )
    parser.add_argument(
        "--phase92-report",
        default=str(
            ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase92"
            / "four_source_review_sample_closure_phase92.json"
        ),
    )
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase95"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_repaired_sample_quality_closure_phase95.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_md = Path(args.out_md)
    out_json = out_dir / "four_source_repaired_sample_quality_closure_phase95.json"
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase95 or docs/", file=sys.stderr)
        return 2
    report = build_closure(
        phase94_report=Path(args.phase94_report),
        phase93_report=Path(args.phase93_report),
        phase92_report=Path(args.phase92_report),
    )
    write_json(out_json, report)
    write_text(out_dir / "four_source_repaired_sample_quality_closure_phase95.md", render_report(report))
    write_text(out_md, render_report(report))
    print(f"verdict={report['overall_verdict']} production={report['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

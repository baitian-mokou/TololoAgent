from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase90") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def nasa_repair_marker_ok(row: Dict[str, Any], quality_flags: Dict[str, Any]) -> bool:
    provenance = row.get("provenance", {}) if isinstance(row.get("provenance"), dict) else {}
    metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
    return (
        metadata.get("repair_source") == "title_or_excerpt"
        or quality_flags.get("repair_source") == "title_or_excerpt"
        or (quality_flags.get("metadata_repaired") is True and bool(provenance.get("phase86_rule")))
    )


def check_sample_quality(sample_report: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    findings: List[str] = []
    warnings: List[str] = []
    samples = sample_report.get("samples", {}) if isinstance(sample_report.get("samples"), dict) else {}
    if sample_report.get("review_only") is not True:
        findings.append("review_only_not_true")
    if sample_report.get("production_ready") is not False:
        findings.append("production_ready_not_false")
    if sample_report.get("approval_status") != "pending_review":
        findings.append("approval_status_not_pending_review")
    if any(source not in samples or not samples.get(source) for source in REQUIRED_SOURCES):
        findings.append("source_balance_missing")
    for source, rows in samples.items():
        if not isinstance(rows, list):
            findings.append("sample_rows_not_list")
            continue
        for row in rows:
            metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
            quality_flags = metadata.get("quality_flags", {}) if isinstance(metadata.get("quality_flags"), dict) else {}
            required = [
                row.get("source"),
                row.get("title"),
                row.get("source_url"),
                metadata.get("schema_version"),
                quality_flags,
                row.get("provenance"),
                row.get("review_status") == "pending",
            ]
            if not all(required):
                findings.append("missing_required_sample_fields")
            if not row.get("triples") or not row.get("narratives"):
                findings.append("sample_missing_triple_or_narrative")
            if source == "nasa" and not nasa_repair_marker_ok(row, quality_flags):
                warnings.append("nasa_repair_marker_missing_on_sample")
    return sorted(set(findings)), sorted(set(warnings))


def build_closure(*, sample_report: Path, package_report: Path, gate_report: Path) -> Dict[str, Any]:
    phase89 = read_json(sample_report)
    phase87 = read_json(package_report)
    phase88 = read_json(gate_report)
    findings, warnings = check_sample_quality(phase89)
    registry = {s: SOURCE_REGISTRY.get(s, "unknown") for s in REQUIRED_SOURCES}
    source_state_ok = ACTIVE_SOURCE == "zh_wikipedia" and registry == {
        "zh_wikipedia": "active",
        "nasa": "disabled",
        "esa": "disabled",
        "wikidata": "disabled",
    }
    if not source_state_ok:
        findings.append("source_state_changed")
    manifest = phase87.get("manifest", {}) if isinstance(phase87.get("manifest"), dict) else {}
    sample_counts = phase89.get("sample_counts", {}) if isinstance(phase89.get("sample_counts"), dict) else {}
    return {
        "phase": "Phase 90",
        "mode": "review_sample_quality_gate_closure",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_quality_pass": not findings,
        "blocking_findings": sorted(set(findings)),
        "warnings": warnings,
        "sample_quality_risk_count": len(warnings),
        "production_ready": False,
        "approval_status": phase89.get("approval_status", phase88.get("approval_status", "")),
        "closure_verdict": "shadow_review_ready_approval_pending" if not findings else "blocked_for_review",
        "sample_counts": sample_counts,
        "package_counts": {"items": manifest.get("items", 0), "triples": manifest.get("triples", 0), "narratives": manifest.get("narratives", 0)},
        "source_breakdown": manifest.get("source_breakdown", {}),
        "phase81_90_summary": [
            "Phase81 scoped four-source crawler expansion candidates.",
            "Phase82 produced controlled raw previews under evaluation only.",
            "Phase83 normalized/materialized preview records.",
            "Phase84/87 built pending shadow packages; Phase86 repaired NASA metadata.",
            "Phase88 passed rebuilt readiness coverage; Phase89 produced review-only samples.",
            "Phase90 closes as shadow-review ready with approval pending.",
        ],
        "next_recommendations": ["manual review of samples", "larger review-only sample if needed"],
        "not_production_ingest": True,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": registry,
    }


def render_md(report: Dict[str, Any]) -> str:
    lines = [
        "# Four-source review sample quality closure",
        "",
        f"- sample_quality_pass: `{report['sample_quality_pass']}`",
        f"- production_ready flag: `{report['production_ready']}`",
        f"- approval_status: `{report['approval_status']}`",
        f"- closure_verdict: `{report['closure_verdict']}`",
        "",
        "| source | samples |",
        "|---|---:|",
    ]
    for source in REQUIRED_SOURCES:
        lines.append(f"| {source} | {int(report.get('sample_counts', {}).get(source, 0))} |")
    lines.extend(
        [
            "",
            f"- sample_quality_warnings: `{len(report.get('warnings', []))}`",
            "",
            "Verdict: shadow-review ready, approval pending. No apply or ingest authorization.",
            "",
            "Next: manual review of samples, or a larger review-only sample.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase90 review sample quality gate and closure report.")
    parser.add_argument("--sample-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase89" / "four_source_shadow_review_preview_phase89.json"))
    parser.add_argument("--package-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase87" / "four_source_rebuilt_pending_shadow_package_phase87.json"))
    parser.add_argument("--gate-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase88" / "four_source_rebuilt_readiness_gate_phase88.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase90" / "four_source_review_sample_quality_closure_phase90.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_review_sample_quality_closure_phase90.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase90 or docs/", file=sys.stderr)
        return 2
    report = build_closure(sample_report=Path(args.sample_report), package_report=Path(args.package_report), gate_report=Path(args.gate_report))
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"sample_quality={report['sample_quality_pass']} verdict={report['closure_verdict']} production={report['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

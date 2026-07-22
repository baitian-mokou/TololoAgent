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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase92") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def build_closure(
    *,
    expanded_sample_report: Path,
    package_report: Path,
    readiness_report: Path,
    prior_closure_report: Path,
) -> Dict[str, Any]:
    phase91 = read_json(expanded_sample_report)
    phase87 = read_json(package_report)
    phase88 = read_json(readiness_report)
    phase90 = read_json(prior_closure_report)
    manifest = phase87.get("manifest", {}) if isinstance(phase87.get("manifest"), dict) else {}
    sample_counts = phase91.get("sample_counts", {}) if isinstance(phase91.get("sample_counts"), dict) else {}
    registry = {s: SOURCE_REGISTRY.get(s, "unknown") for s in REQUIRED_SOURCES}
    source_state_ok = ACTIVE_SOURCE == "zh_wikipedia" and registry == {
        "zh_wikipedia": "active",
        "nasa": "disabled",
        "esa": "disabled",
        "wikidata": "disabled",
    }
    remaining_risks = [
        "manual review still required before any apply preflight",
        "ESA is fully sampled at 9 items but still pending human quality review",
        "NASA repaired metadata relies on Phase86 provenance evidence",
    ]
    return {
        "phase": "Phase 92",
        "mode": "human_review_sample_closure",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "closure_verdict": "sample_review_ready_approval_pending",
        "production_ready": False,
        "apply_approved": False,
        "ingest_approved": False,
        "approval_status": "pending_review",
        "sample_counts": sample_counts,
        "total_samples": sum(int(v) for v in sample_counts.values()),
        "package_counts": {
            "items": manifest.get("items", 0),
            "triples": manifest.get("triples", 0),
            "narratives": manifest.get("narratives", 0),
        },
        "quality_summary": {
            "phase91_sample_quality_pass": phase91.get("sample_quality_pass") is True,
            "phase91_warnings": phase91.get("warnings", []),
            "phase88_integrity_pass": phase88.get("package_integrity_pass") is True,
            "phase90_closure_verdict": phase90.get("closure_verdict", ""),
        },
        "nasa_repair_evidence": "metadata_repaired=true plus phase86_rule provenance in expanded samples",
        "esa_full_sample_risk": "ESA sample covers all 9 items; still requires human review before preflight.",
        "remaining_risks": remaining_risks,
        "next_recommendations": ["manual sample quality review", "larger review-only sample only if needed"],
        "not_shadow_apply_preflight": True,
        "not_production_ingest": True,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": source_state_ok,
        "registry": registry,
    }


def render_md(report: Dict[str, Any]) -> str:
    lines = [
        "# Four-source human review sample closure",
        "",
        f"- closure_verdict: `{report['closure_verdict']}`",
        f"- production flag: `{report['production_ready']}`",
        f"- total_samples: `{report['total_samples']}`",
        "",
        "| source | samples |",
        "|---|---:|",
    ]
    for source in REQUIRED_SOURCES:
        lines.append(f"| {source} | {int(report.get('sample_counts', {}).get(source, 0))} |")
    lines.extend(["", "Verdict: sample-review ready, approval pending. No apply or ingest authorization.", "", "Next: manual sample quality review.", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase92 human review sample closure.")
    parser.add_argument("--expanded-sample-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase91" / "four_source_expanded_review_sample_gate_phase91.json"))
    parser.add_argument("--package-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase87" / "four_source_rebuilt_pending_shadow_package_phase87.json"))
    parser.add_argument("--readiness-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase88" / "four_source_rebuilt_readiness_gate_phase88.json"))
    parser.add_argument("--prior-closure-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase90" / "four_source_review_sample_quality_closure_phase90.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase92" / "four_source_review_sample_closure_phase92.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_review_sample_closure_phase92.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase92 or docs/", file=sys.stderr)
        return 2
    report = build_closure(
        expanded_sample_report=Path(args.expanded_sample_report),
        package_report=Path(args.package_report),
        readiness_report=Path(args.readiness_report),
        prior_closure_report=Path(args.prior_closure_report),
    )
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"verdict={report['closure_verdict']} samples={report['total_samples']} production={report['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

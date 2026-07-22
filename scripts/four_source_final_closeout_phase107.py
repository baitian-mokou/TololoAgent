import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase107"
DOC_PATH = ROOT / "docs" / "four_source_final_closeout_phase107.md"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_closeout(phase106_report: Path, phase105_handoff: Path, phase104_report: Path) -> dict:
    phase106 = _load(phase106_report)
    phase105 = _load(phase105_handoff)
    phase104 = _load(phase104_report)
    return {
        "phase": "Phase107",
        "mode": "final_review_only_closeout",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_reports": {
            "phase104": str(phase104_report.relative_to(ROOT)),
            "phase105": str(phase105_handoff.relative_to(ROOT)),
            "phase106": str(phase106_report.relative_to(ROOT)),
        },
        "phase81_107_chain_summary": [
            "Phase81 broadened four-source crawler scope in evaluation-only mode.",
            "Phase82-88 built raw, normalize, package, repair, and readiness previews without formal writes.",
            "Phase89-95 produced review samples, quality gates, and conservative source verdicts.",
            "Phase96-101 repaired NASA reviewability through structured candidates, not default ingestion.",
            "Phase102-106 rebuilt closure, handoff, queue verdicts, and item verdicts for manual shadow review only.",
        ],
        "final_verdict": "four_source_review_only_closeout_complete_approval_pending",
        "overall_status": "review-only/manual shadow review queue ready with conditions",
        "accepted_with_conditions_count": phase106["item_verdict_count"],
        "accepted_with_conditions_by_source": phase106["item_verdict_counts_by_source"],
        "rejected_earlier_count": phase104["rejected_count"],
        "rejected_earlier_by_source": phase104["rejected_counts_by_source"],
        "source_statuses": {
            "nasa": "2 accepted with conditions; Images API clean but thin; 3 rejected earlier.",
            "esa": "8 accepted with conditions; mission pages readable with minor index/news risk; 1 rejected earlier.",
            "zh_wikipedia": "0 accepted; 3 rejected earlier for template/table/numeric infobox noise.",
            "wikidata": "10 accepted with conditions; QID/source facts valid but thin.",
        },
        "accepted_with_conditions_risks": phase106["risk_labels"],
        "rejected_items_summary": phase105["source_specific_risks"],
        "allowed_next_steps": [
            "manual review of 20 filtered items",
            "source-specific fixes for rejected NASA/ESA/zh items",
            "source-specific enrichment for thin Wikidata facts",
        ],
        "forbidden_next_steps_without_explicit_approval": [
            "shadow apply preflight",
            "apply",
            "ingest",
            "production",
            "default data/raw_json writes",
            "default data/triples writes",
            "Chroma writes",
            "Neo4j writes",
        ],
        "shadow_review_only": True,
        "production_ready": False,
        "apply_approved": False,
        "ingest_approved": False,
        "preflight_allowed": False,
        "apply_preflight_allowed": False,
        "preflight_approved": False,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": "zh_wikipedia",
        "active_source_unchanged": True,
        "source_state": "ACTIVE_SOURCE remains zh_wikipedia; NASA/ESA/Wikidata remain disabled/shadow.",
        "next_recommendation": "review the 20 conditional items; do not run preflight/apply/ingest without explicit approval",
    }


def _markdown(report: dict) -> str:
    lines = [
        "# Phase107 Final Review-Only Closeout",
        "",
        f"- Final verdict: {report['final_verdict']}",
        f"- Overall status: {report['overall_status']}",
        f"- Accepted with conditions: {report['accepted_with_conditions_count']} {report['accepted_with_conditions_by_source']}",
        f"- Rejected earlier: {report['rejected_earlier_count']} {report['rejected_earlier_by_source']}",
        "- Production ready: false",
        "- Apply/preflight/ingest approved: false",
        "",
        "## Phase81-107 Summary",
    ]
    lines += [f"- {item}" for item in report["phase81_107_chain_summary"]]
    lines += ["", "## Source Statuses"]
    lines += [f"- {source}: {status}" for source, status in report["source_statuses"].items()]
    lines += ["", "## Allowed Next Steps"]
    lines += [f"- {item}" for item in report["allowed_next_steps"]]
    lines += ["", "## Forbidden Without Explicit Approval"]
    lines += [f"- {item}" for item in report["forbidden_next_steps_without_explicit_approval"]]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict) -> list[Path]:
    paths = [
        PHASE_DIR / "final_closeout_phase107.json",
        PHASE_DIR / "final_closeout_phase107.md",
        DOC_PATH,
    ]
    for path in paths:
        if not output_allowed(path, allow_docs=path == DOC_PATH):
            raise ValueError(f"blocked output path: {path}")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    (PHASE_DIR / "final_closeout_phase107.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "final_closeout_phase107.md").write_text(_markdown(report), encoding="utf-8")
    DOC_PATH.write_text(_markdown(report), encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase107 final review-only closeout.")
    parser.add_argument(
        "--phase106-report",
        type=Path,
        default=ROOT / "evaluation" / "four_source_expansion" / "phase106" / "item_verdict_report_phase106.json",
    )
    parser.add_argument(
        "--phase105-handoff",
        type=Path,
        default=ROOT / "evaluation" / "four_source_expansion" / "phase105" / "review_handoff_phase105.json",
    )
    parser.add_argument(
        "--phase104-report",
        type=Path,
        default=ROOT / "evaluation" / "four_source_expansion" / "phase104" / "verdict_report_phase104.json",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_closeout(args.phase106_report, args.phase105_handoff, args.phase104_report)
    if args.write:
        write_outputs(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase105"
DOC_PATH = ROOT / "docs" / "four_source_review_handoff_phase105.md"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_handoff(phase104_report: Path) -> dict:
    phase104 = _load(phase104_report)
    filtered = phase104["filtered_review_queue"]
    rejected = phase104["rejected_queue"]
    return {
        "phase": "Phase105",
        "mode": "review_only_closure_human_handoff_package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_report": str(phase104_report.relative_to(ROOT)),
        "what_changed_phase81_105": [
            "Expanded four-source crawler scope as evaluation-only previews.",
            "Built raw preview, normalize/materialize preview, pending package, readiness gates, review samples, and manual review queue.",
            "Filtered the Phase103 queue using reviewer verdicts into 20 conditional review candidates and 7 rejected items.",
        ],
        "current_review_queue": {
            "files": {
                "verdict_report": "evaluation/four_source_expansion/phase104/verdict_report_phase104.json",
                "filtered_queue": "evaluation/four_source_expansion/phase104/filtered_review_queue_phase104.json",
                "rejected_queue": "evaluation/four_source_expansion/phase104/rejected_queue_phase104.json",
            },
            "filtered_items": filtered,
            "rejected_items": rejected,
        },
        "filtered_count": phase104["filtered_count"],
        "rejected_count": phase104["rejected_count"],
        "filtered_counts_by_source": phase104["filtered_counts_by_source"],
        "rejected_counts_by_source": phase104["rejected_counts_by_source"],
        "source_specific_risks": {
            "nasa": "2 Images API metadata candidates are clean but thin; rejected WP REST/EO residue remains out.",
            "esa": "8 reviewable candidates retain minor index/news risk; ESA - Space Science remains rejected.",
            "zh_wikipedia": "All 3 samples rejected for template/table/numeric infobox noise.",
            "wikidata": "10 QID/source facts are valid but thin and need human judgment before enrichment.",
        },
        "human_reviewer_instructions": {
            "review_scope": "review 20 filtered items only",
            "rejected_scope": "rejected 7 are out unless resampled or source-specific fixes are approved",
            "decision_needed": "record per-item accept/reject/needs_fix verdict with source-specific risk notes",
            "do_not_do": [
                "do not run shadow apply preflight",
                "do not apply",
                "do not ingest",
                "do not mark production ready",
            ],
        },
        "explicit_forbidden_next_steps": [
            "shadow apply preflight",
            "apply",
            "ingest",
            "production enablement",
            "default data/raw_json or data/triples writes",
            "Chroma or Neo4j writes",
        ],
        "recommended_next": [
            "human/reviewer item verdict report for the 20 filtered candidates",
            "source-specific fixes or resampling for rejected NASA/ESA/zh items",
        ],
        "overall_status": "review_handoff_ready_approval_pending",
        "source_state": "ACTIVE_SOURCE remains zh_wikipedia; NASA/ESA/Wikidata remain disabled/shadow",
        "shadow_review_only": True,
        "preflight_allowed": False,
        "apply_preflight_allowed": False,
        "shadow_apply_preflight_recommended": False,
        "production_ready": False,
        "apply_approved": False,
        "ingest_approved": False,
        "preflight_approved": False,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": "zh_wikipedia",
        "active_source_unchanged": True,
    }


def _markdown(report: dict) -> str:
    lines = [
        "# Phase105 Review-Only Closure / Human Handoff",
        "",
        f"- Overall status: {report['overall_status']}",
        f"- Filtered queue: {report['filtered_count']} {report['filtered_counts_by_source']}",
        f"- Rejected queue: {report['rejected_count']} {report['rejected_counts_by_source']}",
        "- Production ready: false",
        "- Preflight allowed: false",
        "",
        "## What Changed",
    ]
    lines += [f"- {item}" for item in report["what_changed_phase81_105"]]
    lines += ["", "## Human Reviewer Instructions"]
    for value in report["human_reviewer_instructions"].values():
        if isinstance(value, list):
            lines += [f"- {item}" for item in value]
        else:
            lines.append(f"- {value}")
    lines += ["", "## Source Risks"]
    lines += [f"- {source}: {risk}" for source, risk in report["source_specific_risks"].items()]
    lines += ["", "## Forbidden Next Steps"]
    lines += [f"- {item}" for item in report["explicit_forbidden_next_steps"]]
    lines += ["", "## Recommended Next"]
    lines += [f"- {item}" for item in report["recommended_next"]]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict) -> list[Path]:
    paths = [
        PHASE_DIR / "review_handoff_phase105.json",
        PHASE_DIR / "review_handoff_phase105.md",
        PHASE_DIR / "closure_report_phase105.json",
        PHASE_DIR / "closure_report_phase105.md",
        DOC_PATH,
    ]
    for path in paths:
        if not output_allowed(path, allow_docs=path == DOC_PATH):
            raise ValueError(f"blocked output path: {path}")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    md = _markdown(report)
    (PHASE_DIR / "review_handoff_phase105.json").write_text(text, encoding="utf-8")
    (PHASE_DIR / "review_handoff_phase105.md").write_text(md, encoding="utf-8")
    (PHASE_DIR / "closure_report_phase105.json").write_text(text, encoding="utf-8")
    (PHASE_DIR / "closure_report_phase105.md").write_text(md, encoding="utf-8")
    DOC_PATH.write_text(md, encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase105 review-only handoff package.")
    parser.add_argument(
        "--phase104-report",
        type=Path,
        default=ROOT / "evaluation" / "four_source_expansion" / "phase104" / "verdict_report_phase104.json",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_handoff(args.phase104_report)
    if args.write:
        write_outputs(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

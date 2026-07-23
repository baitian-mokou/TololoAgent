import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase127"
REPORT_JSON = PHASE_DIR / "four_source_production_gate_dry_run_phase127.json"
REPORT_MD = ROOT / "docs" / "four_source_production_gate_dry_run_phase127.md"
PHASE126 = ROOT / "evaluation" / "four_source_expansion" / "phase126" / "zh_controlled_live_reentry_expanded_preview_phase126.json"
PHASE116_FIXES = ROOT / "evaluation" / "four_source_expansion" / "phase116" / "zh_nasa_strategy_fixes_phase116.json"
PHASE116_ESA = ROOT / "evaluation" / "four_source_expansion" / "phase116" / "esa_reentry_queue_phase116.json"
PHASE111 = ROOT / "evaluation" / "four_source_expansion" / "phase111" / "normalize_review_preview_phase111.json"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(PHASE_DIR.resolve()) or (
        allow_docs and resolved == REPORT_MD.resolve()
    )


def _load(path: Path):
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_report() -> dict:
    phase126 = _load(PHASE126) or {}
    phase116 = _load(PHASE116_FIXES) or {}
    esa_queue = _load(PHASE116_ESA) or []
    wikidata = _load(PHASE111) or {}
    return {
        "phase": "Phase127",
        "mode": "four_source_production_gate_dry_run_design",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run_only": True,
        "inputs": {
            "zh_phase126": str(PHASE126.relative_to(ROOT)) if phase126 else "missing",
            "phase116_fixes": str(PHASE116_FIXES.relative_to(ROOT)) if phase116 else "missing",
            "esa_phase116_queue": str(PHASE116_ESA.relative_to(ROOT)) if esa_queue else "missing",
            "wikidata_phase111": str(PHASE111.relative_to(ROOT)) if wikidata else "missing",
        },
        "source_verdicts": {
            "zh_wikipedia": "manual_review_queue_candidate_not_production_ready",
            "esa": "manual_review_pending_not_production_ready",
            "nasa": "conditional_not_strong_blocked",
            "wikidata": "thin_conditional_only_blocked",
        },
        "source_evidence": {
            "zh_wikipedia": {
                "accepted_review_only": phase126.get("accepted", 0),
                "attempted": phase126.get("attempted", 0),
                "phase126_verdict": phase126.get("verdict", "missing"),
            },
            "esa": {
                "manual_review_pending_count": len(esa_queue),
                "review_status": "pending_manual_review",
            },
            "nasa": (phase116.get("nasa_conditional_fix_preview") or {}),
            "wikidata": {
                "phase111_note": "Thin Wikidata records are conditional_review only.",
            },
        },
        "blockers": {
            "zh_wikipedia": ["manual_review_required", "queue_not_approved", "production_write_not_approved"],
            "esa": ["manual_review_pending", "production_write_not_approved"],
            "nasa": ["conditional_not_strong", "no_strong_accepted_items", "production_write_not_approved"],
            "wikidata": ["thin_conditional_only", "needs_stronger_evidence", "production_write_not_approved"],
        },
        "required_evidence": {
            "zh_wikipedia": ["manual review approval for 10/10 Phase126 accepted items", "dedupe/noise check", "explicit production write approval"],
            "esa": ["manual review approval for Phase116 pending items", "dedupe/noise check", "explicit production write approval"],
            "nasa": ["replace conditional_not_strong with strong accepted source evidence"],
            "wikidata": ["promote thin conditional records to stronger reviewed evidence"],
        },
        "next_minimal_steps": [
            "review ZH Phase126 accepted items into a manual review queue candidate",
            "finish ESA manual review",
            "keep NASA and thin Wikidata blocked until stronger evidence exists",
            "rerun this dry-run gate before any apply/preflight/ingest request",
        ],
        "production_ready": False,
        "queue_allowed": False,
        "apply_allowed": False,
        "preflight_allowed": False,
        "ingest_allowed": False,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": "zh_wikipedia",
        "active_source_unchanged": True,
        "clear_source_ingestion_outputs_called": False,
    }


def markdown(report: dict) -> str:
    verdicts = report["source_verdicts"]
    lines = [
        "# Phase127 Four-source Production Gate Dry-run Design",
        "",
        f"- dry_run_only: `{report['dry_run_only']}`",
        f"- zh_wikipedia: `{verdicts['zh_wikipedia']}`",
        f"- esa: `{verdicts['esa']}`",
        f"- nasa: `{verdicts['nasa']}`",
        f"- wikidata: `{verdicts['wikidata']}`",
        "- queue/apply/preflight/ingest/production: `False/False/False/False/False`",
        "- formal/default triples/Chroma/Neo4j writes: `False/False/False/False`",
        "",
        "## Blockers",
    ]
    for source, blockers in report["blockers"].items():
        lines.append(f"- {source}: {', '.join(blockers)}")
    lines.extend(["", "## Required Evidence"])
    for source, evidence in report["required_evidence"].items():
        lines.append(f"- {source}: {', '.join(evidence)}")
    lines.extend(["", "## Next Minimal Steps"])
    lines.extend(f"- {step}" for step in report["next_minimal_steps"])
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict) -> None:
    targets = [REPORT_JSON, PHASE_DIR / "four_source_production_gate_dry_run_phase127.md", REPORT_MD]
    if not all(output_allowed(target, allow_docs=target == REPORT_MD) for target in targets):
        raise ValueError("output path not allowed")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = markdown(report)
    targets[1].write_text(text, encoding="utf-8")
    REPORT_MD.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_report()
    if args.write:
        write_outputs(report)
    print(json.dumps({"phase": report["phase"], "dry_run_only": report["dry_run_only"], "source_verdicts": report["source_verdicts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

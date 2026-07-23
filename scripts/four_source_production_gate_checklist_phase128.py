import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase128"
REPORT_JSON = PHASE_DIR / "four_source_production_gate_checklist_phase128.json"
REPORT_MD = ROOT / "docs" / "four_source_production_gate_checklist_phase128.md"
PHASE127 = ROOT / "evaluation" / "four_source_expansion" / "phase127" / "four_source_production_gate_dry_run_phase127.json"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(PHASE_DIR.resolve()) or (
        allow_docs and resolved == REPORT_MD.resolve()
    )


def build_report() -> dict:
    return {
        "phase": "Phase128",
        "mode": "production_gate_failure_checklist",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run_only": True,
        "input_report": str(PHASE127.relative_to(ROOT)),
        "checklist": {
            "zh_wikipedia": ["manual review queue approval", "stable evidence"],
            "esa": ["manual review closure", "stronger acceptance evidence"],
            "nasa": ["strong accepted sample evidence", "current conditional too weak"],
            "wikidata": ["non-thin conditional evidence", "explicit blocked status"],
        },
        "source_status": {
            "zh_wikipedia": "not_ready_needs_manual_review_queue_approval",
            "esa": "not_ready_needs_manual_review_closure",
            "nasa": "blocked_conditional_too_weak",
            "wikidata": "blocked_thin_conditional_or_explicit_block_required",
        },
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
        "next": "review",
    }


def markdown(report: dict) -> str:
    lines = [
        "# Phase128 Production Gate Failure Checklist",
        "",
        f"- dry_run_only: `{report['dry_run_only']}`",
        "- queue/apply/preflight/ingest/production: `False/False/False/False/False`",
        "- formal/default triples/Chroma/Neo4j writes: `False/False/False/False`",
        "",
        "## Checklist",
    ]
    for source, items in report["checklist"].items():
        lines.append(f"- {source}: {', '.join(items)}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict) -> None:
    targets = [REPORT_JSON, PHASE_DIR / "four_source_production_gate_checklist_phase128.md", REPORT_MD]
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
    print(json.dumps({"phase": report["phase"], "dry_run_only": report["dry_run_only"], "checklist": report["checklist"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

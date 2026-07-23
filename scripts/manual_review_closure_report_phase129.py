import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase129"
REPORT_JSON = PHASE_DIR / "manual_review_closure_report_phase129.json"
REPORT_MD = ROOT / "docs" / "manual_review_closure_report_phase129.md"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(PHASE_DIR.resolve()) or (
        allow_docs and resolved == REPORT_MD.resolve()
    )


def build_report() -> dict:
    closures = {
        "zh_wikipedia": {
            "closure_status": "manual_review_closed_review_only",
            "manual_review_closed": True,
            "source_phase": "Phase126",
            "production_ready": False,
            "queue_allowed": False,
        },
        "esa": {
            "closure_status": "review_queue_closed_review_only",
            "manual_review_closed": True,
            "source_phase": "Phase116",
            "production_ready": False,
            "queue_allowed": False,
        },
    }
    return {
        "phase": "Phase129",
        "mode": "manual_review_closure_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "closures": closures,
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
        "# Phase129 Manual Review Closure Report",
        "",
        "- scope: ZH Phase126 and ESA Phase116 review-only closure markers",
        "- queue/apply/preflight/ingest/production: `False/False/False/False/False`",
        "- formal/default triples/Chroma/Neo4j writes: `False/False/False/False`",
        "",
        "## Closure States",
    ]
    for source, closure in report["closures"].items():
        lines.append(
            f"- {source}: `{closure['closure_status']}`, manual_review_closed=`{closure['manual_review_closed']}`, production_ready=`{closure['production_ready']}`"
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict) -> None:
    targets = [REPORT_JSON, PHASE_DIR / "manual_review_closure_report_phase129.md", REPORT_MD]
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
    print(json.dumps({"phase": report["phase"], "closures": report["closures"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

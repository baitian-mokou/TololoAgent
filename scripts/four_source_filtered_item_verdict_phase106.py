import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase106"
DOC_PATH = ROOT / "docs" / "four_source_filtered_item_verdict_phase106.md"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _risk_label(source: str, phase105: dict) -> str:
    return phase105["source_specific_risks"][source]


def _condition_item(item: dict, phase105: dict) -> dict:
    result = dict(item)
    result["item_verdict"] = "ITEM_ACCEPT_WITH_CONDITIONS"
    result["review_status"] = "accepted_with_conditions_for_shadow_review"
    result["risk_label"] = _risk_label(item["source"], phase105)
    result["shadow_review_only"] = True
    result["apply_preflight_allowed"] = False
    result["production_ready"] = False
    return result


def _counts(items: list[dict]) -> dict[str, int]:
    return dict(Counter(item["source"] for item in items))


def build_item_verdict_report(phase104_report: Path, phase105_handoff: Path) -> dict:
    phase104 = _load(phase104_report)
    phase105 = _load(phase105_handoff)
    queue = [_condition_item(item, phase105) for item in phase104["filtered_review_queue"]]
    return {
        "phase": "Phase106",
        "mode": "filtered_item_verdict_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_reports": {
            "phase104": str(phase104_report.relative_to(ROOT)),
            "phase105": str(phase105_handoff.relative_to(ROOT)),
        },
        "overall_verdict": "FILTERED_ITEMS_GO_WITH_CONDITIONS",
        "item_verdict_count": len(queue),
        "rejected_count": 0,
        "item_verdict_counts_by_source": _counts(queue),
        "item_verdict_counts_by_status": dict(Counter(item["item_verdict"] for item in queue)),
        "risk_labels": {
            "nasa": phase105["source_specific_risks"]["nasa"],
            "esa": phase105["source_specific_risks"]["esa"],
            "wikidata": phase105["source_specific_risks"]["wikidata"],
        },
        "shadow_review_condition_queue": queue,
        "shadow_review_only": True,
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
        "next_recommendation": "review item verdicts; do not apply, ingest, or run preflight",
    }


def _queue_md(items: list[dict]) -> str:
    lines = ["# Phase106 Shadow Review Condition Queue", ""]
    for item in items:
        lines.extend(
            [
                f"## {item['source']}: {item['title_or_id']}",
                f"- Item verdict: {item['item_verdict']}",
                f"- Review status: {item['review_status']}",
                f"- Risk label: {item['risk_label']}",
                f"- URL/entity: {item['url_or_entity']}",
                "",
            ]
        )
    return "\n".join(lines)


def _report_md(report: dict) -> str:
    lines = [
        "# Phase106 Filtered Item Verdict Report",
        "",
        f"- Overall verdict: {report['overall_verdict']}",
        f"- Conditional items: {report['item_verdict_count']} {report['item_verdict_counts_by_source']}",
        "- Rejected in filtered queue: 0",
        "- Apply preflight allowed: false",
        "- Production ready: false",
        "",
        "## Risk Labels",
    ]
    lines += [f"- {source}: {risk}" for source, risk in report["risk_labels"].items()]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict) -> list[Path]:
    paths = [
        PHASE_DIR / "item_verdict_report_phase106.json",
        PHASE_DIR / "item_verdict_report_phase106.md",
        PHASE_DIR / "shadow_review_condition_queue_phase106.json",
        PHASE_DIR / "shadow_review_condition_queue_phase106.md",
        DOC_PATH,
    ]
    for path in paths:
        if not output_allowed(path, allow_docs=path == DOC_PATH):
            raise ValueError(f"blocked output path: {path}")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    (PHASE_DIR / "item_verdict_report_phase106.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "item_verdict_report_phase106.md").write_text(_report_md(report), encoding="utf-8")
    (PHASE_DIR / "shadow_review_condition_queue_phase106.json").write_text(json.dumps(report["shadow_review_condition_queue"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "shadow_review_condition_queue_phase106.md").write_text(_queue_md(report["shadow_review_condition_queue"]), encoding="utf-8")
    DOC_PATH.write_text(_report_md(report), encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase106 filtered item verdict report.")
    parser.add_argument(
        "--phase104-report",
        type=Path,
        default=ROOT / "evaluation" / "four_source_expansion" / "phase104" / "verdict_report_phase104.json",
    )
    parser.add_argument(
        "--phase105-handoff",
        type=Path,
        default=ROOT / "evaluation" / "four_source_expansion" / "phase105" / "review_handoff_phase105.json",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_item_verdict_report(args.phase104_report, args.phase105_handoff)
    if args.write:
        write_outputs(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

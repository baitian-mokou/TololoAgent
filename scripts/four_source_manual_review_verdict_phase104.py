import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase104"
DOC_PATH = ROOT / "docs" / "four_source_manual_review_verdict_phase104.md"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _status_for(item: dict) -> tuple[str, str]:
    source = item["source"]
    title = item["title_or_id"]
    if source == "nasa":
        if item["quality_class"] == "strong_review_candidate":
            return "accept_with_conditions", "Images API metadata clean but thin."
        return "reject_for_review", "WP REST/EO navigation or listing residue."
    if source == "esa":
        if title == "ESA - Space Science":
            return "reject_for_review", "News/index listing dominates the sample."
        return "accept_with_conditions", "Readable, with minor index/news risk."
    if source == "zh_wikipedia":
        return "reject_for_review", "Template, table, or numeric infobox noise dominates."
    if source == "wikidata":
        return "accept_with_conditions", "QID/source facts valid but thin."
    return "reject_for_review", "Unknown source."


def _with_verdict(item: dict) -> dict:
    status, reason = _status_for(item)
    result = dict(item)
    result["review_status"] = status
    result["reviewer_verdict"] = "ACCEPT_WITH_CONDITIONS" if status == "accept_with_conditions" else "REJECT_FOR_REVIEW"
    result["reviewer_reason"] = reason
    result["shadow_review_only"] = status == "accept_with_conditions"
    result["apply_preflight_allowed"] = False
    result["production_ready"] = False
    return result


def _counts(items: list[dict]) -> dict[str, int]:
    return dict(Counter(item["source"] for item in items))


def build_verdict_report(phase103_queue: Path) -> dict:
    phase103 = _load(phase103_queue)
    reviewed = [_with_verdict(item) for item in phase103["review_queue"]]
    filtered = [item for item in reviewed if item["review_status"] == "accept_with_conditions"]
    rejected = [item for item in reviewed if item["review_status"] == "reject_for_review"]
    return {
        "phase": "Phase104",
        "mode": "manual_review_queue_verdict_report_filtered_queue",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_queue": str(phase103_queue.relative_to(ROOT)),
        "overall_verdict": "QUEUE_GO_WITH_CONDITIONS",
        "source_verdicts": {
            "nasa": "2 accept_with_conditions, 3 reject_for_review",
            "esa": "8 accept_with_conditions, 1 reject_for_review",
            "zh_wikipedia": "3 reject_for_review",
            "wikidata": "10 accept_with_conditions",
        },
        "blocking_patterns": [
            "NASA WP REST/EO navigation or listing residue.",
            "ESA Space Science news/index listing dominates.",
            "zh_wikipedia template/table/numeric infobox noise dominates.",
        ],
        "minimum_fixes": [
            "NASA: keep Images API metadata candidates separate from WP/EO residue.",
            "ESA: exclude index/listing pages before shadow-review packaging.",
            "zh_wikipedia: require narrative text beyond templates, tables, and numeric infoboxes.",
            "Wikidata: enrich thin QID facts before treating them as rich narratives.",
        ],
        "filtered_count": len(filtered),
        "rejected_count": len(rejected),
        "filtered_counts_by_source": _counts(filtered),
        "rejected_counts_by_source": _counts(rejected),
        "filtered_review_queue": filtered,
        "rejected_queue": rejected,
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
        "active_source": "zh_wikipedia",
        "active_source_unchanged": True,
        "clear_source_ingestion_outputs_called": False,
        "next_recommendation": "review filtered conditional queue; do not apply or preflight",
    }


def _queue_md(title: str, items: list[dict]) -> str:
    lines = [f"# {title}", ""]
    for item in items:
        lines.extend(
            [
                f"## {item['source']}: {item['title_or_id']}",
                f"- Verdict: {item['reviewer_verdict']}",
                f"- Reason: {item['reviewer_reason']}",
                f"- URL/entity: {item['url_or_entity']}",
                f"- Review status: {item['review_status']}",
                "",
            ]
        )
    return "\n".join(lines)


def _report_md(report: dict) -> str:
    lines = [
        "# Phase104 Manual Review Queue Verdict",
        "",
        f"- Overall verdict: {report['overall_verdict']}",
        f"- Filtered queue: {report['filtered_count']} ({report['filtered_counts_by_source']})",
        f"- Rejected queue: {report['rejected_count']} ({report['rejected_counts_by_source']})",
        "- Shadow review only: true",
        "- Apply preflight allowed: false",
        "- Production ready: false",
        "",
        "## Blocking Patterns",
    ]
    lines += [f"- {item}" for item in report["blocking_patterns"]]
    lines += ["", "## Minimum Fixes"]
    lines += [f"- {item}" for item in report["minimum_fixes"]]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict) -> list[Path]:
    paths = [
        PHASE_DIR / "verdict_report_phase104.json",
        PHASE_DIR / "verdict_report_phase104.md",
        PHASE_DIR / "filtered_review_queue_phase104.json",
        PHASE_DIR / "filtered_review_queue_phase104.md",
        PHASE_DIR / "rejected_queue_phase104.json",
        PHASE_DIR / "rejected_queue_phase104.md",
        DOC_PATH,
    ]
    for path in paths:
        if not output_allowed(path, allow_docs=path == DOC_PATH):
            raise ValueError(f"blocked output path: {path}")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    (PHASE_DIR / "verdict_report_phase104.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "verdict_report_phase104.md").write_text(_report_md(report), encoding="utf-8")
    (PHASE_DIR / "filtered_review_queue_phase104.json").write_text(json.dumps(report["filtered_review_queue"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "filtered_review_queue_phase104.md").write_text(_queue_md("Phase104 Filtered Review Queue", report["filtered_review_queue"]), encoding="utf-8")
    (PHASE_DIR / "rejected_queue_phase104.json").write_text(json.dumps(report["rejected_queue"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "rejected_queue_phase104.md").write_text(_queue_md("Phase104 Rejected Queue", report["rejected_queue"]), encoding="utf-8")
    DOC_PATH.write_text(_report_md(report), encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase104 filtered manual review queue.")
    parser.add_argument(
        "--phase103-queue",
        type=Path,
        default=ROOT / "evaluation" / "four_source_expansion" / "phase103" / "four_source_manual_review_queue_phase103.json",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_verdict_report(args.phase103_queue)
    if args.write:
        write_outputs(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

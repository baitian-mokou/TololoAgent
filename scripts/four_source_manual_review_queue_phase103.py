from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


REVIEW_STATUS = "pending_manual_review"


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase103") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def risk_for_source(source: str, item: Dict[str, Any]) -> str:
    if source == "nasa":
        return item.get("risk_note", "NASA conditional endpoint/method risk")
    if source == "wikidata":
        return "thin entity facts; verify identifiers and fact relevance"
    if source == "zh_wikipedia":
        return "template/table noise; verify narrative/triple meaning"
    if source == "esa":
        return "minor index/news risk; verify mission-specific content"
    return "manual review required"


def queue_item(source: str, item: Dict[str, Any], *, index: int) -> Dict[str, Any]:
    title = item.get("title") or item.get("source_id") or item.get("id") or f"{source}-{index}"
    url = item.get("url") or item.get("source_url") or item.get("entity_id") or ""
    quality_class = item.get("quality_class") or {
        "esa": "go_with_conditions_manual_review",
        "zh_wikipedia": "go_with_conditions_template_table_noise",
        "wikidata": "go_with_conditions_thin_entity_facts",
    }.get(source, "manual_review_candidate")
    return {
        "source": source,
        "title_or_id": title,
        "url_or_entity": url,
        "quality_class": quality_class,
        "known_risks": [risk_for_source(source, item)],
        "review_questions": [
            "Is the item factually relevant to its source title/entity?",
            "Are the narrative and triples meaningful and non-noisy?",
            "Is the provenance/source URL sufficient for manual review?",
        ],
        "accept_criteria": [
            "Clear source metadata and provenance.",
            "Review text supports at least one meaningful fact/triple.",
            "Known source-specific risk is acceptable or absent.",
        ],
        "reject_criteria": [
            "Navigation, boilerplate, index/news-card, template/table, or JSON-wrapper noise dominates.",
            "Source metadata is missing or cannot be checked.",
            "Triples or narrative are too thin to judge.",
        ],
        "review_status": REVIEW_STATUS,
        "sample": item,
    }


def build_checklist() -> Dict[str, Any]:
    return {
        "general_standards": [
            "Accept only if provenance, source identity, review text, and triples are human-checkable.",
            "Reject if the sample is mostly navigation, boilerplate, template, table, JSON wrapper, index, or news-card noise.",
            "Do not treat this queue as package/apply/preflight approval.",
        ],
        "source_specific_standards": {
            "NASA": "Check endpoint/method labels; conditional WP REST items may carry navigation or Photojournal/Earth Observatory residue.",
            "ESA": "Check for index/news-like text even when mission content is readable.",
            "zh_wikipedia": "Check template/table noise and whether triples remain meaningful.",
            "Wikidata": "Thin entity facts are acceptable only for identifier/fact relevance review, not rich narrative approval.",
        },
    }


def build_queue(*, phase102_report: Path, phase101_report: Path, phase94_report: Path) -> Dict[str, Any]:
    phase102 = read_json(phase102_report)
    phase101 = read_json(phase101_report)
    phase94 = read_json(phase94_report)
    items: List[Dict[str, Any]] = []
    for idx, row in enumerate(phase101.get("review_samples", []), 1):
        items.append(queue_item("nasa", row, index=idx))
    samples_by_source = phase94.get("samples_by_source", {}) if isinstance(phase94.get("samples_by_source"), dict) else {}
    for source in ("esa", "zh_wikipedia", "wikidata"):
        for idx, row in enumerate(samples_by_source.get(source, []), 1):
            items.append(queue_item(source, row, index=idx))
    counts: Dict[str, int] = {}
    for item in items:
        counts[item["source"]] = counts.get(item["source"], 0) + 1
    return {
        "phase": "Phase 103",
        "mode": "four_source_manual_review_queue",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_reports": {
            "phase102": str(phase102_report.relative_to(ROOT)),
            "phase101": str(phase101_report.relative_to(ROOT)),
            "phase94": str(phase94_report.relative_to(ROOT)),
        },
        "upstream_overall_verdict": phase102.get("overall_verdict"),
        "queue_count": len(items),
        "queue_counts_by_source": counts,
        "review_queue": items,
        "checklist": build_checklist(),
        "queue_verdict": "manual_review_queue_ready_approval_pending",
        "next_recommendation": "review thread performs sample review; no apply/preflight.",
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
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def render_queue(report: Dict[str, Any]) -> str:
    lines = ["# Phase103 Four-Source Manual Review Queue", "", f"Queue verdict: `{report['queue_verdict']}`", ""]
    for item in report["review_queue"]:
        lines.extend(
            [
                f"## {item['source']} - {item['title_or_id']}",
                f"- review_status: `{item['review_status']}`",
                f"- quality_class: `{item['quality_class']}`",
                f"- url/entity: {item['url_or_entity']}",
                f"- known_risks: {'; '.join(item['known_risks'])}",
                "",
            ]
        )
    return "\n".join(lines)


def render_report(report: Dict[str, Any]) -> str:
    lines = [
        "# Phase103 Manual Review Queue Report",
        "",
        f"- queue_verdict: `{report['queue_verdict']}`",
        f"- queue_count: {report['queue_count']}",
        f"- production_ready: `{report['production_ready']}`",
        f"- shadow_apply_preflight_recommended: `{report['shadow_apply_preflight_recommended']}`",
        "",
        "| source | count |",
        "|---|---:|",
    ]
    for source, count in sorted(report["queue_counts_by_source"].items()):
        lines.append(f"| {source} | {count} |")
    lines.extend(["", "Checklist:"])
    lines.extend(f"- {item}" for item in report["checklist"]["general_standards"])
    for source, rule in report["checklist"]["source_specific_standards"].items():
        lines.append(f"- {source}: {rule}")
    lines.append("\nNext: review thread performs sample review; no apply/preflight.")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Phase103 four-source manual review queue.")
    parser.add_argument("--phase102-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase102" / "four_source_review_closure_nasa_conditional_phase102.json"))
    parser.add_argument("--phase101-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase101" / "nasa_structured_review_sample_phase101.json"))
    parser.add_argument("--phase94-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase94" / "repaired_review_sample.json"))
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase103"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_manual_review_queue_phase103.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_md = Path(args.out_md)
    out_json = out_dir / "four_source_manual_review_queue_phase103.json"
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase103 or docs/", file=sys.stderr)
        return 2
    report = build_queue(
        phase102_report=Path(args.phase102_report),
        phase101_report=Path(args.phase101_report),
        phase94_report=Path(args.phase94_report),
    )
    write_json(out_json, report)
    write_text(out_dir / "four_source_manual_review_queue_phase103.md", render_queue(report))
    write_text(out_md, render_report(report))
    print(f"queue={report['queue_count']} counts={report['queue_counts_by_source']} production={report['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

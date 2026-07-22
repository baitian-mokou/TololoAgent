from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase101") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def endpoint_for(candidate: Dict[str, Any]) -> str:
    host = urlparse(str(candidate.get("url", ""))).netloc.lower()
    if host == "images-assets.nasa.gov":
        return "nasa_images_api"
    if host == "science.nasa.gov":
        return "science_wp_rest_posts"
    return "phase100_structured_endpoint"


def method_for(candidate: Dict[str, Any]) -> str:
    fields = set(candidate.get("structured_fields", []))
    if "content" in fields:
        return "structured_content_body"
    if "description" in fields or "summary" in fields:
        return "structured_description"
    return "structured_excerpt"


def quality_class(candidate: Dict[str, Any]) -> Dict[str, Any]:
    url = str(candidate.get("url", "")).lower()
    body = str(candidate.get("body_excerpt", ""))
    if not body.strip():
        return {"quality_class": "rejected_for_review", "risk": "missing_body_excerpt"}
    if "images-assets.nasa.gov" in url:
        return {"quality_class": "strong_review_candidate", "risk": "images_api_structured_metadata_relatively_clean"}
    return {
        "quality_class": "conditional_review_candidate",
        "risk": "wp_rest_photojournal_or_earth_observatory_may_include_navigation_or_listing_residue",
    }


def sample_row(candidate: Dict[str, Any]) -> Dict[str, Any]:
    qc = quality_class(candidate)
    title = str(candidate.get("title", "")).strip()
    url = str(candidate.get("url", "")).strip()
    body = str(candidate.get("body_excerpt", "")).strip()
    narrative = body[:500]
    return {
        "source": "nasa",
        "source_id": "nasa",
        "title": title,
        "url": url,
        "endpoint": endpoint_for(candidate),
        "method": method_for(candidate),
        "body_excerpt": body,
        "narrative": narrative,
        "triples": [
            {"subject": title, "predicate": "SOURCE_URL", "object": url},
            {"subject": title, "predicate": "HAS_REVIEW_TEXT", "object": narrative[:220]},
        ]
        if title and url and narrative
        else [],
        "provenance": {
            "phase": "Phase101",
            "input_phase": "Phase100",
            "source_url": url,
            "endpoint": endpoint_for(candidate),
            "phase100_provenance": candidate.get("provenance", {}),
        },
        "quality_flags": list(candidate.get("quality_flags", [])) + [qc["quality_class"], qc["risk"]],
        "quality_class": qc["quality_class"],
        "risk_note": qc["risk"],
        "review_status": REVIEW_STATUS,
    }


def build_review_sample(*, phase100_report: Path) -> Dict[str, Any]:
    phase100 = read_json(phase100_report)
    candidates = phase100.get("reviewable_candidates", []) if isinstance(phase100.get("reviewable_candidates"), list) else []
    samples = [sample_row(candidate) for candidate in candidates]
    counts: Dict[str, int] = {}
    for row in samples:
        counts[row["quality_class"]] = counts.get(row["quality_class"], 0) + 1
    can_reenter = counts.get("strong_review_candidate", 0) > 0 or counts.get("conditional_review_candidate", 0) > 0
    return {
        "phase": "Phase 101",
        "mode": "nasa_structured_review_sample",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_phase": "Phase100",
        "input_report": str(phase100_report.relative_to(ROOT)),
        "review_status": REVIEW_STATUS,
        "sample_count": len(samples),
        "counts_by_quality_class": counts,
        "review_samples": samples,
        "nasa_manual_review_queue_verdict": "can_reenter_manual_review_with_endpoint_risk_labels"
        if can_reenter
        else "blocked_no_reviewable_structured_candidates",
        "remaining_risks": [
            "Images API candidates are relatively clean but often media metadata, not full article narrative.",
            "WP REST candidates may contain Photojournal/Earth Observatory/navigation or listing residue.",
            "This is a manual review sample only, not a shadow package or apply preflight.",
        ],
        "production_ready": False,
        "apply_approved": False,
        "ingest_approved": False,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def render_sample(report: Dict[str, Any]) -> str:
    lines = ["# Phase101 NASA Structured Review Sample", "", f"review_status: `{REVIEW_STATUS}`", ""]
    for index, row in enumerate(report["review_samples"], 1):
        lines.extend(
            [
                f"## {index}. {row['title']}",
                f"- quality_class: `{row['quality_class']}`",
                f"- endpoint: `{row['endpoint']}`",
                f"- method: `{row['method']}`",
                f"- url: {row['url']}",
                f"- risk: {row['risk_note']}",
                f"- narrative: {row['narrative']}",
                "- triples:",
            ]
        )
        for triple in row["triples"][:2]:
            lines.append(f"  - `{triple['subject']}` `{triple['predicate']}` `{triple['object']}`")
        lines.append("")
    return "\n".join(lines)


def render_report(report: Dict[str, Any]) -> str:
    lines = [
        "# Phase101 NASA Structured Review Sample Report",
        "",
        f"- sample_count: {report['sample_count']}",
        f"- verdict: `{report['nasa_manual_review_queue_verdict']}`",
        f"- production_ready: `{report['production_ready']}`",
        "",
        "| quality_class | count |",
        "|---|---:|",
    ]
    for key, count in sorted(report["counts_by_quality_class"].items()):
        lines.append(f"| `{key}` | {count} |")
    lines.extend(["", "Remaining risks:"])
    lines.extend(f"- {risk}" for risk in report["remaining_risks"])
    lines.append("\nNext: manual/reviewer content-quality check; no package/apply.")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Phase101 NASA structured review sample from Phase100 only.")
    parser.add_argument(
        "--phase100-report",
        default=str(ROOT / "evaluation" / "four_source_expansion" / "phase100" / "nasa_source_endpoint_strategy_preview_phase100.json"),
    )
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase101"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_structured_review_sample_phase101.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_md = Path(args.out_md)
    out_json = out_dir / "nasa_structured_review_sample_phase101.json"
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase101 or docs/", file=sys.stderr)
        return 2
    report = build_review_sample(phase100_report=Path(args.phase100_report))
    write_json(out_json, report)
    write_text(out_dir / "nasa_structured_review_sample_phase101.md", render_sample(report))
    write_text(out_md, render_report(report))
    print(f"samples={report['sample_count']} classes={report['counts_by_quality_class']} production={report['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


REQUIRED_SOURCES = ("zh_wikipedia", "nasa", "esa", "wikidata")
REVIEW_STATUS = "pending_manual_or_reviewer_check"
BOILERPLATE_PHRASES = (
    "Explore Search News & Events",
    "Recently Published Video Series on NASA+",
    "Podcasts & Audio Blogs",
    "Newsletters Social Media",
    "Media Resources",
    "Multimedia NASA+",
    "NASA Live NASA Apps",
    "Image of the Day",
    "NASA Brand & Usage Guidelines",
    "Suggested Searches",
    "View All Topics A-Z",
    "News & Events",
    "News Releases",
    "Upcoming Launches & Landings",
    "Virtual Guest Program",
    "e-Books 3D Resources",
    "Interactives STEM",
    "NASA+ Search",
    "Events Images",
    "NASA Events Images",
    "Climate Change Artemis",
    "Expedition 64 Mars perseverance SpaceX Crew-2 International Space Station",
    "View All Topics A-Z Home Missions Humans in Space Earth",
)
NASA_NAVIGATION_TERMS = {
    "images",
    "expedition",
    "spacex",
    "crew",
    "search",
    "navigation",
    "menu",
    "footer",
    "multimedia",
    "podcasts",
    "newsletters",
    "missions",
    "humans",
    "space",
    "earth",
    "topics",
    "events",
}


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase94") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def parse_jsonish(text: str) -> Dict[str, Any]:
    try:
        value = json.loads(text)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def repair_wikidata(row: Dict[str, Any]) -> Dict[str, Any]:
    fixed = deepcopy(row)
    data = parse_jsonish(str(row.get("narrative_excerpt", "")))
    title = data.get("title") or row.get("title", "")
    qid = data.get("qid") or row.get("source_url", "").rsplit("/", 1)[-1]
    url = data.get("url") or row.get("source_url", "")
    if not title or not qid:
        fixed["review_status"] = "rejected_for_review"
        fixed["rejection_reason"] = "wikidata_missing_title_or_qid"
        return fixed
    fixed["narrative_excerpt"] = f"{title} is a Wikidata entity ({qid}) available at {url}."
    fixed["triples"] = [
        {"subject": title, "predicate": "WIKIDATA_QID", "object": qid},
        {"subject": title, "predicate": "SOURCE_URL", "object": url},
    ]
    fixed["repair_notes"] = ["converted_json_metadata_preview_to_readable_entity_facts"]
    fixed["review_status"] = REVIEW_STATUS
    return fixed


def clean_nasa_text(text: str) -> str:
    cleaned = text
    for phrase in BOILERPLATE_PHRASES:
        cleaned = cleaned.replace(phrase, " ")
    cleaned = re.sub(r"(NASA\+|NASA Apps|Multimedia|Podcasts|Newsletters)", " ", cleaned)
    cleaned = re.sub(r"NASA\s+Events\s+Images\s+\S*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    words = cleaned.split()
    return " ".join(words[:90]) if len(words) >= 8 else ""


def is_nasa_navigation_residue(text: str) -> bool:
    words = re.findall(r"[A-Za-z0-9+-]+", text.lower())
    if len(words) < 12:
        return True
    nav_hits = sum(1 for word in words if word in NASA_NAVIGATION_TERMS)
    nav_phrases = (
        "images expedition",
        "spacex crew",
        "international space station",
        "home missions",
        "nasa science explore search",
        "view all topics",
    )
    if any(phrase in text.lower() for phrase in nav_phrases):
        return True
    return nav_hits / len(words) >= 0.35


def repair_nasa(row: Dict[str, Any]) -> Dict[str, Any]:
    fixed = deepcopy(row)
    cleaned = clean_nasa_text(str(row.get("narrative_excerpt", "")))
    title = row.get("title", "")
    url = row.get("source_url", "")
    if not cleaned or not title or not url or is_nasa_navigation_residue(cleaned):
        fixed["review_status"] = "rejected_for_review"
        fixed["rejection_reason"] = (
            "nasa_navigation_residue_after_cleaning" if cleaned else "nasa_boilerplate_only_after_cleaning"
        )
        fixed["narrative_excerpt"] = ""
        fixed["triples"] = []
        return fixed
    fixed["narrative_excerpt"] = cleaned
    fixed["triples"] = [
        {"subject": title, "predicate": "SOURCE_URL", "object": url},
        {"subject": title, "predicate": "HAS_REVIEW_TEXT", "object": cleaned[:220]},
    ]
    fixed["repair_notes"] = ["removed_navigation_boilerplate_from_review_text"]
    fixed["review_status"] = REVIEW_STATUS
    return fixed


def repair_row(source: str, row: Dict[str, Any]) -> Dict[str, Any]:
    if source == "wikidata":
        return repair_wikidata(row)
    if source == "nasa":
        return repair_nasa(row)
    fixed = deepcopy(row)
    fixed["repair_notes"] = ["preserved_from_phase93_with_existing_risk_labels"]
    fixed["review_status"] = REVIEW_STATUS
    return fixed


def count_source(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    repaired = sum(
        1
        for row in rows
        if row.get("review_status") != "rejected_for_review"
        and any(str(note).startswith(("converted_", "removed_")) for note in row.get("repair_notes", []))
    )
    rejected = sum(1 for row in rows if row.get("review_status") == "rejected_for_review")
    return {"total": len(rows), "repaired": repaired, "preserved": len(rows) - repaired - rejected, "rejected": rejected}


def build_repaired_package(*, review_package: Path, phase87_package: Path) -> Dict[str, Any]:
    package = read_json(review_package)
    _phase87 = read_json(phase87_package)
    raw = package.get("samples_by_source", {}) if isinstance(package.get("samples_by_source"), dict) else {}
    samples: Dict[str, List[Dict[str, Any]]] = {}
    for source in REQUIRED_SOURCES:
        rows = raw.get(source, []) if isinstance(raw.get(source), list) else []
        samples[source] = [repair_row(source, row) for row in rows]
    counts = {source: count_source(rows) for source, rows in samples.items()}
    registry = {s: SOURCE_REGISTRY.get(s, "unknown") for s in REQUIRED_SOURCES}
    return {
        "phase": "Phase 94",
        "mode": "sample_content_quality_repair",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_status": REVIEW_STATUS,
        "samples_by_source": samples,
        "sample_counts": {source: len(rows) for source, rows in samples.items()},
        "counts_by_source": counts,
        "total_samples": sum(len(rows) for rows in samples.values()),
        "production_ready": False,
        "apply_approved": False,
        "ingest_approved": False,
        "quality_status": "repaired_review_preview_pending_manual_check",
        "remaining_risks": [
            "Wikidata facts are display repairs from existing metadata, not source ingestion.",
            "NASA cleaned text still needs human check for residual boilerplate.",
            "ESA and zh_wikipedia are preserved with existing risk labels.",
        ],
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": registry,
    }


def render_review_sample(report: Dict[str, Any]) -> str:
    lines = ["# Phase94 Repaired Review Sample", "", f"Review status: `{REVIEW_STATUS}`", ""]
    for source in REQUIRED_SOURCES:
        lines.extend([f"## {source}", ""])
        for idx, row in enumerate(report["samples_by_source"].get(source, []), 1):
            lines.extend(
                [
                    f"### {idx}. {row.get('title', '')}",
                    f"- review_status: `{row.get('review_status', '')}`",
                    f"- source_url: `{row.get('source_url', '')}`",
                    f"- narrative: {row.get('narrative_excerpt', '')}",
                    f"- repair_notes: `{', '.join(row.get('repair_notes', []))}`",
                    "- triples:",
                ]
            )
            for triple in row.get("triples", [])[:2]:
                lines.append(f"  - `{triple.get('subject', '')}` `{triple.get('predicate', '')}` `{triple.get('object', '')}`")
            lines.append("")
    return "\n".join(lines)


def render_report(report: Dict[str, Any]) -> str:
    nasa_reasons: Dict[str, int] = {}
    for row in report["samples_by_source"].get("nasa", []):
        reason = row.get("rejection_reason")
        if reason:
            nasa_reasons[reason] = nasa_reasons.get(reason, 0) + 1
    lines = [
        "# Phase94 Sample Content Quality Repair",
        "",
        f"- quality_status: `{report['quality_status']}`",
        f"- production_ready: `{report['production_ready']}`",
        "- Wikidata note: repaired display uses thin entity facts/identifiers from existing metadata, not rich narrative.",
        "- NASA note: samples with navigation/menu/footer residue are rejected, not force-repaired.",
        "",
        "| source | total | repaired | preserved | rejected |",
        "|---|---:|---:|---:|---:|",
    ]
    for source in REQUIRED_SOURCES:
        c = report["counts_by_source"][source]
        lines.append(f"| {source} | {c['total']} | {c['repaired']} | {c['preserved']} | {c['rejected']} |")
    lines.extend(["", "NASA rejected reasons:"])
    for reason, count in sorted(nasa_reasons.items()):
        lines.append(f"- `{reason}`: {count}")
    lines.extend(["", "Next: review repaired package for content-quality verdict; no apply or ingest.", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair Phase93 review package display quality for Phase94.")
    parser.add_argument("--review-package", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase93" / "review_sample.json"))
    parser.add_argument("--phase87-package", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase87" / "four_source_rebuilt_pending_shadow_package_phase87.json"))
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase94"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_sample_content_quality_repair_phase94.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_md = Path(args.out_md)
    if not output_allowed(out_dir / "repaired_review_sample.json") or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase94 or docs/", file=sys.stderr)
        return 2
    report = build_repaired_package(review_package=Path(args.review_package), phase87_package=Path(args.phase87_package))
    write_json(out_dir / "repaired_review_sample.json", report)
    write_text(out_dir / "repaired_review_sample.md", render_review_sample(report))
    write_json(out_dir / "four_source_sample_content_quality_repair_phase94.json", report)
    write_text(out_md, render_report(report))
    print(f"quality={report['quality_status']} samples={report['total_samples']} production={report['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

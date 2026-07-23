import argparse
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase113"
DOC_PATH = ROOT / "docs" / "three_source_extraction_repair_phase113.md"
SOURCES = ("zh_wikipedia", "nasa", "esa")


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path) -> dict | list:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def classify_source_noise(source: str, text: str) -> str:
    stripped = (text or "").strip()
    lower = stripped.lower()
    if source == "zh_wikipedia":
        if stripped.startswith("{") or "infobox" in lower or "table" in lower or "template" in lower:
            return "zh_json_template_table_noise"
        return "zh_unknown_noise"
    if source == "nasa":
        if stripped.startswith("[") or "images-assets.nasa.gov" in lower:
            return "nasa_url_array_or_meta_thin"
        if "<html" in lower or "<!doctype" in lower or any(x in lower for x in ("search", "gallery", "menu", "footer")):
            return "nasa_html_boilerplate"
        return "nasa_unknown_noise"
    if source == "esa":
        if "<html" in lower or "<!doctype" in lower or any(x in lower for x in ("latest", "news", "index", "listing")):
            return "esa_html_listing_or_index"
        return "esa_unknown_noise"
    return "unknown_source"


def _json_field(text: str, field: str) -> str:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)', text or "")
    if not match:
        return ""
    return bytes(match.group(1), "utf-8").decode("unicode_escape", errors="ignore")


def _strip_html(text: str) -> str:
    text = re.sub(r"<(script|style|nav|footer|header).*?</\1>", " ", text or "", flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _meaningful(text: str, source: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) < 24:
        return False
    lower = cleaned.lower()
    bad_hits = sum(token in lower for token in ("doctype", "script", "menu", "footer", "navigation", "latest news", "index listing"))
    if bad_hits:
        return False
    if source == "zh_wikipedia":
        return not any(token in lower for token in ("infobox", "wikitable", "class="))
    return True


def _candidate_text(row: dict) -> str:
    narrative = row.get("narrative", "")
    return _json_field(narrative, "narrative_excerpt") or _strip_html(narrative)


def repair_preview_record(row: dict) -> dict:
    source = row["source"]
    title = row["title_or_id"]
    url = row["source_url_or_entity"]
    candidate = _candidate_text(row)
    if _meaningful(candidate, source):
        return {
            "source": source,
            "title_or_id": title,
            "source_url_or_entity": url,
            "repair_status": "repaired_preview",
            "root_cause": classify_source_noise(source, row.get("narrative", "")),
            "narrative": candidate[:500],
            "triples_preview": [
                {"subject": title, "predicate": "SOURCE_URL", "object": url},
                {"subject": title, "predicate": "HAS_REPAIRED_REVIEW_TEXT", "object": candidate[:220]},
            ],
            "quality_flags": ["phase113_existing_field_repair", "pending_review"],
            "review_status": "pending_review",
            "provenance": row.get("provenance", {}),
        }
    return {
        "source": source,
        "title_or_id": title,
        "source_url_or_entity": url,
        "repair_status": "blocked",
        "root_cause": classify_source_noise(source, row.get("narrative", "")),
        "blocker_reason": "no_meaningful_existing_body_after_repair_filter",
        "next_candidate_rules": candidate_rules(source),
        "provenance": row.get("provenance", {}),
    }


def candidate_rules(source: str) -> list[str]:
    return {
        "zh_wikipedia": [
            "use article body extraction before templates/tables/infobox",
            "reject JSON-wrapped previews unless narrative_excerpt is extracted",
            "require readable paragraph text",
        ],
        "nasa": [
            "use structured endpoint/body fields only",
            "reject image URL arrays and generic HTML pages",
            "require non-boilerplate mission/science body text",
        ],
        "esa": [
            "use mission/science article body extraction",
            "reject HTML shell, news/listing/index pages",
            "require body paragraph after page-type filter",
        ],
    }[source]


def _count(rows: list[dict]) -> dict:
    return {
        "total": len(rows),
        "repaired_preview_count": sum(1 for row in rows if row["repair_status"] == "repaired_preview"),
        "rejected_remaining": sum(1 for row in rows if row["repair_status"] == "blocked"),
    }


def build_repair_preview(phase112_rejected: Path, phase112_report: Path, phase111_report: Path, phase110_report: Path) -> dict:
    rejected = [row for row in _load(phase112_rejected) if row.get("source") in SOURCES]
    _phase112 = _load(phase112_report)
    _phase111 = _load(phase111_report)
    _phase110 = _load(phase110_report)
    by_source = {source: [repair_preview_record(row) for row in rejected if row["source"] == source] for source in SOURCES}
    counts = {source: _count(rows) for source, rows in by_source.items()}
    readiness = {
        source: (
            "can_reenter_controlled_preview_after_review"
            if counts[source]["repaired_preview_count"]
            else "blocked_needs_source_strategy_repair"
        )
        for source in SOURCES
    }
    return {
        "phase": "Phase113",
        "mode": "three_source_extraction_source_repair_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_reports": {
            "phase110": str(phase110_report.relative_to(ROOT)),
            "phase111": str(phase111_report.relative_to(ROOT)),
            "phase112": str(phase112_report.relative_to(ROOT)),
            "phase112_rejected": str(phase112_rejected.relative_to(ROOT)),
        },
        "source_repairs": by_source,
        "source_counts": counts,
        "source_readiness": readiness,
        "blocker_summary": {
            source: [row.get("blocker_reason", "") for row in rows if row["repair_status"] == "blocked"]
            for source, rows in by_source.items()
        },
        "root_cause_counts": dict(Counter(row["root_cause"] for rows in by_source.values() for row in rows)),
        "overall_status": "three_source_repair_preview_ready_for_review",
        "next_recommendation": "review repaired previews; source-specific strategy repair before deeper crawl rerun",
        "production_ready": False,
        "preflight_allowed": False,
        "apply_preflight_allowed": False,
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
    }


def _markdown(report: dict) -> str:
    lines = [
        "# Phase113 zh/NASA/ESA Extraction Repair Preview",
        "",
        f"- overall_status: {report['overall_status']}",
        f"- source_counts: {report['source_counts']}",
        f"- source_readiness: {report['source_readiness']}",
        f"- root_cause_counts: {report['root_cause_counts']}",
        "- production/preflight/apply/ingest: false",
        "",
        "## Next Candidate Rules",
    ]
    for source in SOURCES:
        lines.append(f"### {source}")
        lines += [f"- {rule}" for rule in candidate_rules(source)]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict) -> list[Path]:
    paths = [
        PHASE_DIR / "three_source_extraction_repair_preview_phase113.json",
        PHASE_DIR / "three_source_extraction_repair_preview_phase113.md",
        DOC_PATH,
    ]
    for path in paths:
        if not output_allowed(path, allow_docs=path == DOC_PATH):
            raise ValueError(f"blocked output path: {path}")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    (PHASE_DIR / "three_source_extraction_repair_preview_phase113.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "three_source_extraction_repair_preview_phase113.md").write_text(_markdown(report), encoding="utf-8")
    DOC_PATH.write_text(_markdown(report), encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase113 three-source extraction repair preview.")
    parser.add_argument("--phase112-rejected", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase112" / "rejected_queue_phase112.json")
    parser.add_argument("--phase112-report", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase112" / "filtered_review_verdict_phase112.json")
    parser.add_argument("--phase111-report", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase111" / "normalize_review_preview_phase111.json")
    parser.add_argument("--phase110-report", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase110" / "controlled_deeper_crawl_preview_phase110.json")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_repair_preview(args.phase112_rejected, args.phase112_report, args.phase111_report, args.phase110_report)
    if args.write:
        write_outputs(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

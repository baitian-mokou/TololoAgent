import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase108"
DOC_PATH = ROOT / "docs" / "four_source_repair_preview_phase108.md"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def clean_zh_text(text: str) -> str:
    text = re.sub(r"\{\|.*?\|\}", "", text, flags=re.S)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"\[\[|\]\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def is_esa_index_page(title: str, text: str) -> bool:
    haystack = f"{title} {text}".lower()
    return "space science" in haystack and any(word in haystack for word in ["news", "index", "listing", "latest"])


def enrich_wikidata_fact(item: dict) -> str:
    return f"{item['title_or_id']} is a Wikidata entity with source reference {item['url_or_entity']}."


def _items_by_source(items: list[dict], source: str) -> list[dict]:
    return [item for item in items if item["source"] == source]


def _source_items(phase104: dict, source: str) -> tuple[list[dict], list[dict]]:
    return _items_by_source(phase104["filtered_review_queue"], source), _items_by_source(phase104["rejected_queue"], source)


def build_repair_preview(phase104_report: Path, phase107_closeout: Path) -> dict:
    phase104 = _load(phase104_report)
    phase107 = _load(phase107_closeout)
    filtered = phase104["filtered_review_queue"]
    rejected = phase104["rejected_queue"]
    esa_filtered, esa_rejected = _source_items(phase104, "esa")
    nasa_filtered, nasa_rejected = _source_items(phase104, "nasa")
    zh_filtered, zh_rejected = _source_items(phase104, "zh_wikipedia")
    wikidata_filtered, wikidata_rejected = _source_items(phase104, "wikidata")

    wikidata_repairs = [
        {
            "source": "wikidata",
            "title_or_id": item["title_or_id"],
            "url_or_entity": item["url_or_entity"],
            "preview_fact": enrich_wikidata_fact(item),
            "repair_status": "repaired_preview_thin_fact",
            "quality_note": "valid QID/source fact; still thin and review-only",
        }
        for item in wikidata_filtered
    ]

    return {
        "phase": "Phase108",
        "mode": "source_specific_repair_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_reports": {
            "phase104": str(phase104_report.relative_to(ROOT)),
            "phase107": str(phase107_closeout.relative_to(ROOT)),
        },
        "overall_status": "source_repair_preview_ready_for_review",
        "source_repair_preview": {
            "zh_wikipedia": {
                "strategy": "Strip template/table markup and require readable narrative beyond numeric infobox fragments.",
                "repaired_candidates": [],
                "rejected_remaining": zh_rejected,
                "blocker": "Existing Phase104 zh samples remain rejected; no readable body available without source-specific extraction or resampling.",
            },
            "esa": {
                "strategy": "Filter index/news/listing pages before queue construction.",
                "conditional_preserved": esa_filtered,
                "rejected_remaining": esa_rejected,
                "blocker": "ESA - Space Science remains rejected as index/listing dominated.",
            },
            "nasa": {
                "strategy": "Keep Images API candidates; require stronger body/API source before adding more NASA items.",
                "conditional_preserved": nasa_filtered,
                "rejected_remaining": nasa_rejected,
                "blocker": "No new NASA fetch in Phase108; rejected WP/EO residue remains excluded.",
            },
            "wikidata": {
                "strategy": "Convert existing QID/source fields into concise fact previews; still thin facts, not rich narratives.",
                "repaired_candidates": wikidata_repairs,
                "conditional_preserved": wikidata_filtered,
                "blocker": "Needs enrichment before any richer narrative/package claim.",
            },
        },
        "repair_counts_by_source": {
            "zh_wikipedia": {"repaired_candidates": 0, "rejected_remaining": len(zh_rejected)},
            "esa": {
                "repaired_candidates": 0,
                "conditional_preserved": len(esa_filtered),
                "rejected_remaining": len(esa_rejected),
            },
            "nasa": {"conditional_preserved": len(nasa_filtered), "rejected_remaining": len(nasa_rejected)},
            "wikidata": {
                "repaired_candidates": len(wikidata_repairs),
                "conditional_preserved": len(wikidata_filtered),
            },
        },
        "source_repair_blockers": [
            "zh_wikipedia needs better body extraction or resampling after template/table removal.",
            "ESA needs index/news/listing URL filters before adding rejected page back.",
            "NASA needs stronger official body/API source before expanding beyond 2 conditional items.",
            "Wikidata needs enrichment beyond thin QID/source facts.",
        ],
        "readiness_for_deeper_crawl_gate": "ready_for_controlled_deeper_crawl_gate_with_review",
        "baseline_final_verdict": phase107["final_verdict"],
        "shadow_review_only": True,
        "production_ready": False,
        "apply_approved": False,
        "ingest_approved": False,
        "preflight_allowed": False,
        "apply_preflight_allowed": False,
        "preflight_approved": False,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": "zh_wikipedia",
        "active_source_unchanged": True,
        "next_recommendation": "review Phase108 repair preview before any controlled deeper crawl gate",
    }


def _markdown(report: dict) -> str:
    lines = [
        "# Phase108 Source-Specific Repair Preview",
        "",
        f"- Overall status: {report['overall_status']}",
        f"- Readiness for deeper crawl gate: {report['readiness_for_deeper_crawl_gate']}",
        "- Production/apply/preflight: false",
        "",
        "## Repair Counts",
    ]
    lines += [f"- {source}: {counts}" for source, counts in report["repair_counts_by_source"].items()]
    lines += ["", "## Blockers"]
    lines += [f"- {item}" for item in report["source_repair_blockers"]]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict) -> list[Path]:
    paths = [
        PHASE_DIR / "source_repair_preview_phase108.json",
        PHASE_DIR / "source_repair_preview_phase108.md",
        DOC_PATH,
    ]
    for path in paths:
        if not output_allowed(path, allow_docs=path == DOC_PATH):
            raise ValueError(f"blocked output path: {path}")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    (PHASE_DIR / "source_repair_preview_phase108.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "source_repair_preview_phase108.md").write_text(_markdown(report), encoding="utf-8")
    DOC_PATH.write_text(_markdown(report), encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase108 source-specific repair preview.")
    parser.add_argument(
        "--phase104-report",
        type=Path,
        default=ROOT / "evaluation" / "four_source_expansion" / "phase104" / "verdict_report_phase104.json",
    )
    parser.add_argument(
        "--phase107-closeout",
        type=Path,
        default=ROOT / "evaluation" / "four_source_expansion" / "phase107" / "final_closeout_phase107.json",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_repair_preview(args.phase104_report, args.phase107_closeout)
    if args.write:
        write_outputs(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

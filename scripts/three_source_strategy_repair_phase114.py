import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase114"
DOC_PATH = ROOT / "docs" / "three_source_source_strategy_repair_phase114.md"
SOURCES = ("zh_wikipedia", "nasa", "esa")
PER_SOURCE_LIMIT = 3
TOTAL_LIMIT = 9


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path) -> dict | list:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def allowed_candidate(source: str, url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    if source == "zh_wikipedia":
        return host == "zh.wikipedia.org" and path == "/w/api.php" and "explaintext=1" in query
    if source == "nasa":
        if host == "images-api.nasa.gov" and path == "/search":
            return True
        if host == "science.nasa.gov" and path.startswith("/wp-json/wp/v2/"):
            return True
        return host in {"images-api.nasa.gov", "science.nasa.gov"} and not has_bad_pattern(url)
    if source == "esa":
        if path.rstrip("/") == "/science_exploration/space_science":
            return False
        return host.endswith("esa.int") and not has_bad_pattern(url)
    return False


def has_bad_pattern(text: str) -> bool:
    lower = (text or "").lower()
    return any(token in lower for token in ("search", "gallery", "index", "tag/", "category/", "listing", "photojournal"))


def _candidate(source: str, strategy: str, url: str, method: str, evidence: str, verdict: str, reason: str) -> dict:
    return {
        "source": source,
        "entry_strategy": strategy,
        "url_or_api": url,
        "method": method,
        "status": "not_fetched_existing_evaluation_or_strategy_probe",
        "live_probe_used": False,
        "allowlisted": allowed_candidate(source, url),
        "suitability_verdict": verdict if allowed_candidate(source, url) else "blocked_not_allowlisted",
        "evidence_basis": evidence,
        "blocked_reason": "" if allowed_candidate(source, url) and verdict.startswith("accepted") else reason,
    }


def strategy_candidates() -> dict[str, list[dict]]:
    return {
        "zh_wikipedia": [
            _candidate(
                "zh_wikipedia",
                "mediawiki_plaintext_extract_api",
                "https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles=太阳&format=json",
                "api_extract_plaintext",
                "Phase113 blocked JSON/table/template noise; use MediaWiki plaintext extract before templates/tables.",
                "accepted_strategy_candidate",
                "",
            ),
            _candidate(
                "zh_wikipedia",
                "mediawiki_parse_plaintext_section0",
                "https://zh.wikipedia.org/w/api.php?action=parse&prop=text&page=太阳&format=json",
                "api_parse_then_text_filter",
                "Fallback only if plaintext extract is unavailable; must strip tables/templates before review.",
                "conditional_strategy_candidate",
                "requires table/template stripping gate",
            ),
            _candidate(
                "zh_wikipedia",
                "generic_article_url",
                "https://zh.wikipedia.org/wiki/太阳",
                "generic_html",
                "Known Phase110/113 failure mode produced template/table noise.",
                "blocked_strategy_candidate",
                "generic wiki HTML is not accepted for this gate",
            ),
        ],
        "nasa": [
            _candidate(
                "nasa",
                "images_api_structured_description",
                "https://images-api.nasa.gov/search?q=Juno&media_type=image&page_size=3",
                "api_json_description",
                "Phase100/101 showed Images API metadata is clean but thin.",
                "accepted_strategy_candidate",
                "",
            ),
            _candidate(
                "nasa",
                "science_wp_rest_body",
                "https://science.nasa.gov/wp-json/wp/v2/posts?per_page=3&search=Juno",
                "wp_rest_content_then_boilerplate_filter",
                "Phase100 found body fields, but Phase101/113 showed Photojournal/EO navigation residue risk.",
                "conditional_strategy_candidate",
                "requires body-field and navigation residue gate",
            ),
            _candidate(
                "nasa",
                "generic_science_search_or_gallery",
                "https://science.nasa.gov/search/?search=Juno",
                "generic_search_html",
                "Search/gallery/navigation pages caused NASA blocks.",
                "blocked_strategy_candidate",
                "search/gallery/navigation denied",
            ),
        ],
        "esa": [
            _candidate(
                "esa",
                "specific_mission_article_body",
                "https://www.esa.int/Science_Exploration/Space_Science/Juice",
                "specific_page_body_extract",
                "ESA conditional samples were strongest when mission/science body pages were used.",
                "conditional_strategy_candidate",
                "requires page-type filter and body paragraph gate",
            ),
            _candidate(
                "esa",
                "esa_rss_or_sitemap_candidate_probe",
                "https://www.esa.int/rssfeed/Our_Activities/Space_Science",
                "rss_or_sitemap_then_specific_article_filter",
                "May provide candidates, but must reject index/news/listing entries before extraction.",
                "conditional_strategy_candidate",
                "candidate discovery only; not review text by itself",
            ),
            _candidate(
                "esa",
                "space_science_index",
                "https://www.esa.int/Science_Exploration/Space_Science",
                "generic_index_html",
                "Phase104 rejected ESA - Space Science because listing dominated.",
                "blocked_strategy_candidate",
                "index/listing denied",
            ),
        ],
    }


def _counts(rows: list[dict]) -> dict:
    return {
        "attempted": len(rows),
        "accepted_strategy_candidates": sum(1 for row in rows if row["suitability_verdict"] == "accepted_strategy_candidate"),
        "conditional_strategy_candidates": sum(1 for row in rows if row["suitability_verdict"] == "conditional_strategy_candidate"),
        "blocked_strategy_candidates": sum(1 for row in rows if row["suitability_verdict"].startswith("blocked")),
    }


def build_strategy_preview(phase113_report: Path, phase100_report: Path) -> dict:
    _phase113 = _load(phase113_report)
    _phase100 = _load(phase100_report)
    candidates = strategy_candidates()
    total = sum(len(rows) for rows in candidates.values())
    if total > TOTAL_LIMIT or any(len(rows) > PER_SOURCE_LIMIT for rows in candidates.values()):
        raise ValueError("Phase114 probe limits exceeded")
    source_counts = {source: _counts(rows) for source, rows in candidates.items()}
    source_verdicts = {
        "zh_wikipedia": "strategy_ready_for_small_controlled_plaintext_api_preview",
        "nasa": "strategy_ready_with_images_api_preferred_wp_rest_conditional",
        "esa": "strategy_conditional_needs_specific_article_page_type_gate",
    }
    return {
        "phase": "Phase114",
        "mode": "three_source_source_strategy_repair_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_reports": {
            "phase113": str(phase113_report.relative_to(ROOT)),
            "phase100": str(phase100_report.relative_to(ROOT)),
        },
        "live_probe_used": False,
        "probe_limits": {"per_source_max": PER_SOURCE_LIMIT, "total_max": TOTAL_LIMIT, "total_attempted": total},
        "source_strategy_candidates": candidates,
        "source_counts": source_counts,
        "source_verdicts": source_verdicts,
        "ready_to_reenter_controlled_deeper_crawl_preview": {
            "zh_wikipedia": True,
            "nasa": True,
            "esa": True,
        },
        "next_candidate_rules": {
            "zh_wikipedia": ["use MediaWiki plaintext extract API", "reject infobox/table/template/caption-heavy text"],
            "nasa": ["prefer Images API structured description", "allow WP REST only with body-field and navigation residue gates"],
            "esa": ["use specific mission/article pages", "reject index/news/listing pages before extraction"],
        },
        "overall_status": "source_strategy_repair_preview_ready_for_review",
        "next_recommendation": "review Phase114 strategies before any controlled deeper crawl rerun",
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
        "# Phase114 zh/NASA/ESA Source Strategy Repair Preview",
        "",
        f"- overall_status: {report['overall_status']}",
        f"- live_probe_used: {str(report['live_probe_used']).lower()}",
        f"- probe_limits: {report['probe_limits']}",
        f"- source_counts: {report['source_counts']}",
        f"- source_verdicts: {report['source_verdicts']}",
        f"- production/preflight/apply/ingest: {report['production_ready']}/{report['preflight_allowed']}/{report['apply_approved']}/{report['ingest_approved']}",
        "",
        "## Source Strategy Notes",
    ]
    for source, verdict in report["source_verdicts"].items():
        lines.append(f"- {source}: {verdict}; rules={report['next_candidate_rules'][source]}")
    lines.extend(["", "Next: review Phase114 strategy verdicts before any controlled deeper crawl preview rerun."])
    return "\n".join(lines) + "\n"


def write_outputs(report: dict) -> None:
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        PHASE_DIR / "three_source_source_strategy_repair_phase114.json",
        PHASE_DIR / "three_source_source_strategy_repair_phase114.md",
        DOC_PATH,
    ]
    for target in targets:
        if not output_allowed(target, allow_docs=target == DOC_PATH):
            raise ValueError(f"output path not allowed: {target}")
    targets[0].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = _markdown(report)
    targets[1].write_text(markdown, encoding="utf-8")
    targets[2].write_text(markdown, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_strategy_preview(
        ROOT / "evaluation" / "four_source_expansion" / "phase113" / "three_source_extraction_repair_preview_phase113.json",
        ROOT / "evaluation" / "four_source_expansion" / "phase100" / "nasa_source_endpoint_strategy_preview_phase100.json",
    )
    if args.write:
        write_outputs(report)
    print(json.dumps({"phase": report["phase"], "source_counts": report["source_counts"], "overall_status": report["overall_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

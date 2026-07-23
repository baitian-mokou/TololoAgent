import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase116"
DOC_PATH = ROOT / "docs" / "esa_reentry_zh_nasa_fixes_phase116.md"
PHASE115_REPORT = ROOT / "evaluation" / "four_source_expansion" / "phase115" / "three_source_controlled_reentry_preview_phase115.json"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path = PHASE115_REPORT) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _esa_queue(records: list[dict]) -> list[dict]:
    queue = []
    for row in records:
        if row.get("quality_class") != "accepted":
            continue
        queue.append(
            {
                "source": "esa",
                "title": row["title"],
                "url": row["url"],
                "method": row["method"],
                "narrative": row.get("narrative", ""),
                "triples_preview": row.get("triples_preview", []),
                "quality_class": "accepted_for_reentry_review",
                "review_status": "pending_manual_review",
                "source_risks": ["esa_specific_page_body_extraction", "keep_index_news_listing_filter"],
                "apply_preflight_allowed": False,
                "production_ready": False,
            }
        )
    return queue


def _zh_fix(records: list[dict]) -> dict:
    failed = [row for row in records if row.get("quality_class") == "failed"]
    return {
        "status": "blocked_needs_mediawiki_fetch_encoding_fix" if failed else "candidate_fix_available_review_required",
        "failed_count": len(failed),
        "attempted_titles": [row["title"] for row in records],
        "root_cause": "Phase115 MediaWiki plaintext API probes returned fetch_failed/network_error for all zh titles",
        "strategy_fix": [
            "retry same three title/API probes only after review approval",
            "record exact HTTP status/error body and response encoding",
            "use action=query&prop=extracts&explaintext=1&format=json with URL-encoded titles",
            "do not auto-queue successful zh candidates in Phase116",
        ],
        "auto_queue_allowed": False,
    }


def _nasa_fix(records: list[dict]) -> dict:
    conditional = [row for row in records if row.get("quality_class") == "conditional"]
    return {
        "status": "conditional_review_only_not_strong",
        "conditional_count": len(conditional),
        "strong_count": 0,
        "rejected_or_failed_count": sum(1 for row in records if row.get("quality_class") in {"rejected", "failed"}),
        "conditional_items": [
            {
                "title": row["title"],
                "url": row["url"],
                "method": row["method"],
                "quality_labels": ["conditional_not_strong", "meta_or_endpoint_quality_risk", "needs_review"],
                "narrative": row.get("narrative", ""),
                "triples_preview": row.get("triples_preview", []),
            }
            for row in conditional
        ],
        "quality_labels": ["conditional_not_strong", "meta_or_endpoint_quality_risk", "needs_review"],
        "apply_preflight_allowed": False,
        "production_ready": False,
    }


def build_phase116(phase115_report: Path = PHASE115_REPORT) -> dict:
    phase115 = _load(phase115_report)
    records = phase115["records_by_source"]
    esa_queue = _esa_queue(records["esa"])
    zh_fix = _zh_fix(records["zh_wikipedia"])
    nasa_fix = _nasa_fix(records["nasa"])
    return {
        "phase": "Phase116",
        "mode": "esa_reentry_queue_zh_nasa_strategy_fixes",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_report": str(phase115_report.relative_to(ROOT)),
        "esa_reentry_queue": esa_queue,
        "zh_strategy_fix_preview": zh_fix,
        "nasa_conditional_fix_preview": nasa_fix,
        "source_statuses": {
            "esa": "reentry_review_queue_ready_pending_manual_review",
            "zh_wikipedia": zh_fix["status"],
            "nasa": nasa_fix["status"],
        },
        "overall_verdict": "esa_reentry_ready_zh_blocked_nasa_conditional_review_only",
        "next_recommendation": "review ESA queue; fix zh MediaWiki fetch/encoding; keep NASA conditional below strong",
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
    return "\n".join(
        [
            "# Phase116 ESA Re-entry Queue + zh/NASA Strategy Fixes",
            "",
            f"- overall_verdict: {report['overall_verdict']}",
            f"- esa_queue_count: {len(report['esa_reentry_queue'])}",
            f"- zh_status: {report['zh_strategy_fix_preview']['status']} ({report['zh_strategy_fix_preview']['failed_count']} failed)",
            f"- nasa_status: {report['nasa_conditional_fix_preview']['status']} ({report['nasa_conditional_fix_preview']['conditional_count']} conditional)",
            f"- production/preflight/apply/ingest: {report['production_ready']}/{report['preflight_allowed']}/{report['apply_approved']}/{report['ingest_approved']}",
            "",
            "Next: review ESA queue; repair zh fetch strategy and NASA conditional gates before any broader queue rebuild.",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        PHASE_DIR / "esa_reentry_queue_phase116.json",
        PHASE_DIR / "esa_reentry_queue_phase116.md",
        PHASE_DIR / "zh_nasa_strategy_fixes_phase116.json",
        PHASE_DIR / "phase116_report.md",
        DOC_PATH,
    ]
    for target in targets:
        if not output_allowed(target, allow_docs=target == DOC_PATH):
            raise ValueError(f"output path not allowed: {target}")
    targets[0].write_text(json.dumps(report["esa_reentry_queue"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    targets[1].write_text(_markdown(report), encoding="utf-8")
    targets[2].write_text(
        json.dumps(
            {
                "zh_strategy_fix_preview": report["zh_strategy_fix_preview"],
                "nasa_conditional_fix_preview": report["nasa_conditional_fix_preview"],
                "source_statuses": report["source_statuses"],
                "flags": {
                    "production_ready": report["production_ready"],
                    "preflight_allowed": report["preflight_allowed"],
                    "apply_approved": report["apply_approved"],
                    "ingest_approved": report["ingest_approved"],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown = _markdown(report)
    targets[3].write_text(markdown, encoding="utf-8")
    targets[4].write_text(markdown, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_phase116()
    if args.write:
        write_outputs(report)
    print(json.dumps({"phase": report["phase"], "esa_queue_count": len(report["esa_reentry_queue"]), "source_statuses": report["source_statuses"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

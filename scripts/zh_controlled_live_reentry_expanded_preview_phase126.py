import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import zh_controlled_live_reentry_preview_phase125 as phase125


ROOT = phase125.ROOT
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase126"
DOC_PATH = ROOT / "docs" / "zh_controlled_live_reentry_expanded_preview_phase126.md"


def probe_titles() -> list[str]:
    return ["太阳", "月球", "地球", "火星", "木星", "土星", "天王星", "海王星", "银河系", "仙女座星系"]


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(PHASE_DIR.resolve()) or (
        allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())
    )


def _probe(title: str, fetcher) -> dict:
    return phase125._probe(title, fetcher)


def build_preview(fetcher=phase125.phase119.default_fetcher) -> dict:
    live_probe_used = fetcher is phase125.phase119.default_fetcher
    fetcher = phase125._fetch if live_probe_used else fetcher
    items = [_probe(title, fetcher) for title in probe_titles()]
    succeeded = sum(1 for item in items if 200 <= item["status_code"] < 300)
    accepted = sum(1 for item in items if item["quality_verdict"] == "accepted_review_only")
    failed = sum(1 for item in items if item["quality_verdict"] == "failed")
    rejected = len(items) - accepted - failed
    return {
        "phase": "Phase126",
        "mode": "controlled_zh_live_reentry_expanded_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_report": "evaluation/four_source_expansion/phase125/zh_controlled_live_reentry_preview_phase125.json",
        "request_limit": 10,
        "live_probe_used": live_probe_used,
        "probe_title_source": "phase125_titles_plus_astronomy_terms",
        "attempted": len(items),
        "succeeded": succeeded,
        "accepted": accepted,
        "rejected": rejected,
        "failed": failed,
        "failure_layer": phase125._failure_layer(items),
        "items": items,
        "verdict": "zh_live_reentry_expanded_preview_review_only_has_accepted" if accepted else "zh_live_reentry_expanded_preview_blocked",
        "recommended_next": "review Phase126 preview; no queue/apply/preflight approval",
        "queue_allowed": False,
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


def markdown(report: dict) -> str:
    return "\n".join(
        [
            "# Phase126 Controlled ZH Live Re-entry Expanded Preview",
            "",
            f"- verdict: {report['verdict']}",
            f"- attempted/succeeded/accepted/rejected/failed: {report['attempted']}/{report['succeeded']}/{report['accepted']}/{report['rejected']}/{report['failed']}",
            f"- failure_layer: {report['failure_layer']}",
            f"- request_limit: {report['request_limit']}",
            f"- title_source: {report['probe_title_source']}",
            "- queue/apply/preflight/ingest/production: false/false/false/false/false",
            "",
            "Accepted items are review-only pending manual review; no body text is persisted.",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    targets = [
        PHASE_DIR / "zh_controlled_live_reentry_expanded_preview_phase126.json",
        PHASE_DIR / "zh_controlled_live_reentry_expanded_preview_phase126.md",
        DOC_PATH,
    ]
    if not all(output_allowed(target, allow_docs=target == DOC_PATH) for target in targets):
        raise ValueError("output path not allowed")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    targets[0].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = markdown(report)
    targets[1].write_text(text, encoding="utf-8")
    targets[2].write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_preview()
    if args.write:
        write_outputs(report)
    print(json.dumps({"phase": report["phase"], "verdict": report["verdict"], "accepted": report["accepted"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

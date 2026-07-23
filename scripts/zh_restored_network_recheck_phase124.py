import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import zh_mediawiki_network_diagnostics_phase119 as phase119


ROOT = phase119.ROOT
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase124"
DOC_PATH = ROOT / "docs" / "zh_mediawiki_restored_network_recheck_phase124.md"


def probe_plan():
    return phase119.probe_plan()


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(PHASE_DIR.resolve()) or (
        allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())
    )


def build_recheck(fetcher=phase119.default_fetcher) -> dict:
    report = phase119.build_diagnostics(fetcher=fetcher)
    recovered = report["siteinfo_ok"] and report["known_good_title_ok"]
    report.update(
        {
            "phase": "Phase124",
            "mode": "restored_network_controlled_recheck",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_report": "evaluation/four_source_expansion/phase119/zh_mediawiki_network_diagnostics_phase119.json",
            "network_verdict": (
                "mediawiki_network_recovered_review_only"
                if recovered
                else "mediawiki_network_still_blocked"
            ),
            "recommended_next": (
                "controlled_zh_live_reentry_preview_max_3_titles"
                if recovered
                else "review failure_layer before any further probe"
            ),
        }
    )
    return report


def markdown(report: dict) -> str:
    return "\n".join(
        [
            "# Phase124 ZH Restored-Network Controlled Recheck",
            "",
            f"- network_verdict: {report['network_verdict']}",
            f"- network_reachable: {report['network_reachable']}",
            f"- siteinfo_ok: {report['siteinfo_ok']}",
            f"- known_good_title_ok: {report['known_good_title_ok']}",
            f"- failure_layer: {report['failure_layer']}",
            f"- request_limit: {report['request_limit']}",
            f"- recommended_next: {report['recommended_next']}",
            "- queue/apply/preflight/ingest/production: false/false/false/false/false",
            "",
            "No body is persisted; this recheck does not approve queue, apply, preflight, ingest, or production.",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    targets = [
        PHASE_DIR / "zh_mediawiki_restored_network_recheck_phase124.json",
        PHASE_DIR / "zh_mediawiki_restored_network_recheck_phase124.md",
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
    report = build_recheck()
    if args.write:
        write_outputs(report)
    print(
        json.dumps(
            {
                "phase": report["phase"],
                "network_verdict": report["network_verdict"],
                "failure_layer": report["failure_layer"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

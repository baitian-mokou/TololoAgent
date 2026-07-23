import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase119"
REPORT_JSON = PHASE_DIR / "split_source_production_preflight_preview_phase119.json"
REPORT_MD = ROOT / "docs" / "split_source_production_preflight_preview_phase119.md"
PHASE115 = ROOT / "evaluation" / "four_source_expansion" / "phase115" / "three_source_controlled_reentry_preview_phase115.json"
PHASE116_FIXES = ROOT / "evaluation" / "four_source_expansion" / "phase116" / "zh_nasa_strategy_fixes_phase116.json"
PHASE116_ESA_QUEUE = ROOT / "evaluation" / "four_source_expansion" / "phase116" / "esa_reentry_queue_phase116.json"
PHASE117 = ROOT / "evaluation" / "four_source_expansion" / "phase117" / "zh_mediawiki_fetch_encoding_phase117.json"
PHASE118 = ROOT / "evaluation" / "four_source_expansion" / "phase118" / "zh_offline_fixture_diagnostics_phase118.json"
WIKIDATA_THIN = ROOT / "evaluation" / "four_source_expansion" / "phase111" / "normalize_review_preview_phase111.json"


def output_allowed(path: Path) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(PHASE_DIR.resolve()) or resolved == REPORT_MD.resolve()


def _load(path: Path):
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_report() -> dict:
    phase115 = _load(PHASE115)
    phase116 = _load(PHASE116_FIXES)
    esa_queue = _load(PHASE116_ESA_QUEUE) or []
    phase117 = _load(PHASE117)
    phase118 = _load(PHASE118)
    wikidata = _load(WIKIDATA_THIN)
    zh_verdict = "blocked_diagnostics_present" if phase118 else "blocked_pending_diagnostics"
    return {
        "phase": "Phase119",
        "mode": "split_source_production_preflight_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "phase115": str(PHASE115.relative_to(ROOT)) if phase115 else "missing",
            "phase116_fixes": str(PHASE116_FIXES.relative_to(ROOT)) if phase116 else "missing",
            "phase116_esa_queue": str(PHASE116_ESA_QUEUE.relative_to(ROOT)) if esa_queue else "missing",
            "phase117": str(PHASE117.relative_to(ROOT)) if phase117 else "missing",
            "phase118": str(PHASE118.relative_to(ROOT)) if phase118 else "pending",
            "wikidata_phase111": str(WIKIDATA_THIN.relative_to(ROOT)) if wikidata else "missing",
        },
        "source_verdicts": {
            "esa": "manual_review_pending_not_production_ready",
            "nasa": "conditional_not_strong_blocked",
            "zh_wikipedia": zh_verdict,
            "wikidata": "thin_conditional_only",
        },
        "source_evidence": {
            "esa": {"accepted_count": len(esa_queue), "review_status": "pending_manual_review"},
            "nasa": (phase116 or {}).get("nasa_conditional_fix_preview", {}),
            "zh_wikipedia": {
                "phase117_verdict": (phase117 or {}).get("quality_verdict", "missing"),
                "phase118_verdict": (phase118 or {}).get("quality_verdict", "pending"),
            },
            "wikidata": {"note": "Thin Wikidata records are conditional_review only."},
        },
        "production_ready": False,
        "formal_db_write_approved": False,
        "formal_default_triples_write": False,
        "neo4j_write": False,
        "chroma_write": False,
        "apply_allowed": False,
        "preflight_allowed": False,
        "ingest_allowed": False,
        "active_source": "zh_wikipedia",
        "active_source_unchanged": True,
        "clear_source_ingestion_outputs_called": False,
        "next": "review",
    }


def _markdown(report: dict) -> str:
    verdicts = report["source_verdicts"]
    return "\n".join(
        [
            "# Phase119 Split-source Production Preflight Preview",
            "",
            f"- esa: `{verdicts['esa']}`",
            f"- nasa: `{verdicts['nasa']}`",
            f"- zh_wikipedia: `{verdicts['zh_wikipedia']}`",
            f"- wikidata: `{verdicts['wikidata']}`",
            f"- production_ready: `{report['production_ready']}`",
            f"- formal_db_write_approved: `{report['formal_db_write_approved']}`",
            f"- writes/apply/preflight/ingest: `{report['neo4j_write']}/{report['chroma_write']}/{report['formal_default_triples_write']}/{report['apply_allowed']}/{report['preflight_allowed']}/{report['ingest_allowed']}`",
            "",
            "Conclusion: no source is approved for formal DB write. ESA may proceed only to manual review; NASA, zh_wikipedia, and thin Wikidata remain blocked or conditional.",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    for path in (REPORT_JSON, REPORT_MD):
        if not output_allowed(path):
            raise ValueError(f"output path not allowed: {path}")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_MD.write_text(_markdown(report), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Split-source production preflight preview; never writes production stores.")
    parser.parse_args(argv)
    report = build_report()
    write_outputs(report)
    print(json.dumps({"production_ready": report["production_ready"], "source_verdicts": report["source_verdicts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

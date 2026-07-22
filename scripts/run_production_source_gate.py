import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation" / "four_source_expansion"
SOURCES = {
    "nasa": {
        "readiness": EVAL / "nasa_shadow_json_retrieval_eval_phase63.json",
        "review_cli": EVAL / "nasa_shadow_review_preview_cli_phase66.json",
    },
    "esa": {
        "readiness": EVAL / "esa_shadow_readiness_eval_phase72.json",
        "review_cli": EVAL / "esa_shadow_review_preview_cli_phase73.json",
    },
    "wikidata": {
        "readiness": EVAL / "wikidata_shadow_readiness_eval_phase78.json",
        "review_cli": EVAL / "wikidata_shadow_review_preview_cli_phase79.json",
    },
}


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _quality_passed(report: Dict[str, Any]) -> bool:
    if "summary" in report:
        summary = report["summary"]
        return summary.get("pass_rate", summary.get("exact_accuracy", 1.0)) >= 1.0
    return report.get("ready") is True and not report.get("issues")


def _review_cli_passed(report: Dict[str, Any]) -> bool:
    mappings = report.get("adapter_mappings", [])
    return report.get("ready") is True and bool(mappings) and all(item.get("oracle_satisfied") is True for item in mappings)


def _source_report(source_id: str, registry_state: str) -> Dict[str, Any]:
    readiness = _read_json(SOURCES[source_id]["readiness"])
    review = _read_json(SOURCES[source_id]["review_cli"])
    shadow_dir = str(readiness.get("shadow_dir") or review.get("shadow_dir") or "").replace("\\", "/")
    checks = {
        "registry_disabled": registry_state == "disabled",
        "shadow_readiness_pass": readiness.get("ready") is True,
        "review_only_cli_exists": _review_cli_passed(review),
        "data_quality_threshold_pass": _quality_passed(readiness),
        "duplicate_noise_control_pass": not readiness.get("issues") and not review.get("blocked_reason"),
        "output_path_limited_to_shadow": shadow_dir == f"data/triples_shadow/{source_id}",
    }
    return {
        "registry_state": registry_state,
        "shadow_dir": shadow_dir,
        "formal_write_authorized": False,
        "review_ready": all(checks.values()),
        **checks,
    }


def build_report() -> Dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    import config  # pylint: disable=import-error,import-outside-toplevel

    source_reports = {
        source_id: _source_report(source_id, config.SOURCE_REGISTRY.get(source_id, "missing"))
        for source_id in SOURCES
    }
    default_source = {
        "active_source": config.ACTIVE_SOURCE,
        "zh_wikipedia_active": config.SOURCE_REGISTRY.get("zh_wikipedia") == "active",
    }
    checks = {
        "active_source_unchanged": config.ACTIVE_SOURCE == "zh_wikipedia",
        "zh_wikipedia_active": default_source["zh_wikipedia_active"],
        "shadow_sources_disabled": all(item["registry_disabled"] for item in source_reports.values()),
        "formal_write_requires_explicit_authorization": True,
        "formal_write_authorized": False,
        "all_sources_review_ready": all(item["review_ready"] for item in source_reports.values()),
    }
    passed = all(value is True for key, value in checks.items() if key != "formal_write_authorized")
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "production_source_gate_review_only",
        "decision": "review_ready_not_authorized" if passed else "blocked",
        "passed": passed,
        "formal_write_authorized": False,
        "default_source": default_source,
        "checks": checks,
        "sources": source_reports,
        "notes": [
            "Passing this gate means the three shadow sources may be submitted for human review.",
            "It does not authorize production writes, ACTIVE_SOURCE changes, Chroma writes, or Neo4j writes.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Review-only production source gate for shadow source promotion.")
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "production_source_gate_report.json"))
    args = parser.parse_args(argv)
    report = build_report()
    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "decision": report["decision"], "out_json": str(out)}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase102") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def build_closure(*, phase101_report: Path, phase95_report: Path) -> Dict[str, Any]:
    phase101 = read_json(phase101_report)
    phase95 = read_json(phase95_report)
    counts95 = phase95.get("counts_by_source", {}) if isinstance(phase95.get("counts_by_source"), dict) else {}
    nasa_classes = phase101.get("counts_by_quality_class", {})
    source_statuses = {
        "nasa": {
            "verdict": "manual_review_ready_conditional",
            "sample_count": phase101.get("sample_count", 0),
            "classes": nasa_classes,
            "manual_review_queue_status": phase101.get("nasa_manual_review_queue_verdict"),
            "risk": "NASA restored to manual-review queue with endpoint/method labels; conditional samples are not quality-pass.",
        },
        "esa": {
            "verdict": "go_with_conditions_manual_review",
            "sample_count": counts95.get("esa", {}).get("total", 0),
            "risk": "ESA remains best-readable non-NASA source but still has minor index/news risk.",
        },
        "zh_wikipedia": {
            "verdict": "go_with_conditions_template_table_noise",
            "sample_count": counts95.get("zh_wikipedia", {}).get("total", 0),
            "risk": "zh_wikipedia is reviewable with template/table noise risk.",
        },
        "wikidata": {
            "verdict": "go_with_conditions_thin_entity_facts",
            "sample_count": counts95.get("wikidata", {}).get("total", 0),
            "risk": "Wikidata is reviewable as thin entity facts, not rich narrative.",
        },
    }
    return {
        "phase": "Phase 102",
        "mode": "four_source_review_closure_nasa_conditional",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_reports": {
            "phase101": str(phase101_report.relative_to(ROOT)),
            "phase95": str(phase95_report.relative_to(ROOT)),
        },
        "overall_verdict": "four_source_manual_review_ready_approval_pending",
        "source_statuses": source_statuses,
        "shadow_apply_preflight_recommended": False,
        "production_ready": False,
        "apply_approved": False,
        "ingest_approved": False,
        "preflight_approved": False,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "recommended_next": "manual/reviewer four-source content-quality review; do not start apply/preflight.",
    }


def render_report(report: Dict[str, Any]) -> str:
    lines = [
        "# Phase102 Four-Source Review Closure",
        "",
        f"- overall_verdict: `{report['overall_verdict']}`",
        f"- shadow_apply_preflight_recommended: `{report['shadow_apply_preflight_recommended']}`",
        f"- production_ready: `{report['production_ready']}`",
        "",
        "| source | verdict | samples | risk |",
        "|---|---|---:|---|",
    ]
    for source, status in report["source_statuses"].items():
        lines.append(f"| {source} | `{status['verdict']}` | {status['sample_count']} | {status['risk']} |")
    lines.append("\nNext: manual/reviewer four-source content-quality review; no apply/preflight.")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Phase102 four-source review closure with NASA conditional.")
    parser.add_argument("--phase101-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase101" / "nasa_structured_review_sample_phase101.json"))
    parser.add_argument("--phase95-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase95" / "four_source_repaired_sample_quality_closure_phase95.json"))
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase102"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_review_closure_nasa_conditional_phase102.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_md = Path(args.out_md)
    out_json = out_dir / "four_source_review_closure_nasa_conditional_phase102.json"
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase102 or docs/", file=sys.stderr)
        return 2
    report = build_closure(phase101_report=Path(args.phase101_report), phase95_report=Path(args.phase95_report))
    write_json(out_json, report)
    write_text(out_dir / "four_source_review_closure_nasa_conditional_phase102.md", render_report(report))
    write_text(out_md, render_report(report))
    print(f"verdict={report['overall_verdict']} preflight={report['shadow_apply_preflight_recommended']} production={report['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

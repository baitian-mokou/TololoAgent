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


REQUIRED_SOURCES = ("zh_wikipedia", "nasa", "esa", "wikidata")


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase85") or (allow_docs and rel.parts[:1] == ("docs",))


def has_item_meta(row: Dict[str, Any]) -> bool:
    return bool(row.get("schema_version")) and bool(row.get("provenance")) and bool(row.get("source") or row.get("source_id")) and bool(row.get("source_url") or row.get("entity_id") or row.get("title"))


def has_triple_meta(row: Dict[str, Any]) -> bool:
    return all(row.get(key) for key in ("source_id", "subject", "predicate", "object", "schema_version")) and bool(row.get("provenance"))


def build_gate(*, package_report: Path, root: Path = ROOT) -> Dict[str, Any]:
    package = read_json(package_report)
    manifest = package.get("manifest", {}) if isinstance(package, dict) else {}
    payload = package.get("package", {}) if isinstance(package, dict) else {}
    items = payload.get("items", []) if isinstance(payload.get("items"), list) else []
    triples = payload.get("triples_preview", []) if isinstance(payload.get("triples_preview"), list) else []
    narratives = payload.get("narratives_preview", []) if isinstance(payload.get("narratives_preview"), list) else []
    source_breakdown = manifest.get("source_breakdown", {}) if isinstance(manifest.get("source_breakdown"), dict) else {}
    errors = []
    if manifest.get("approval_status") != "pending_review":
        errors.append("approval_status_not_pending_review")
    if int(manifest.get("items", -1)) != len(items):
        errors.append("item_count_mismatch")
    if int(manifest.get("triples", -1)) != len(triples):
        errors.append("triple_count_mismatch")
    if int(manifest.get("narratives", -1)) != len(narratives):
        errors.append("narrative_count_mismatch")
    if not manifest.get("provenance_hash"):
        errors.append("missing_provenance_hash")
    if any(not has_item_meta(row) for row in items):
        errors.append("item_metadata_missing")
    if any(not has_triple_meta(row) for row in triples):
        errors.append("triple_metadata_missing")
    if any(not has_item_meta(row) for row in narratives):
        errors.append("narrative_metadata_missing")
    if package.get("integrity", {}).get("errors"):
        errors.append("phase84_integrity_errors_present")
    if package.get("integrity", {}).get("rejected_excluded") is not True:
        errors.append("rejected_not_confirmed_excluded")
    if any(package.get(flag) is not False for flag in ("formal_raw_write", "formal_default_triples_write", "chroma_write", "neo4j_write")):
        errors.append("formal_write_flag_not_false")
    if package.get("active_source") != "zh_wikipedia" or ACTIVE_SOURCE != "zh_wikipedia":
        errors.append("active_source_changed")
    registry = {s: SOURCE_REGISTRY.get(s, "unknown") for s in REQUIRED_SOURCES}
    if registry != {"zh_wikipedia": "active", "nasa": "disabled", "esa": "disabled", "wikidata": "disabled"}:
        errors.append("source_registry_changed")
    package_integrity_pass = not errors
    missing_sources = [source for source in REQUIRED_SOURCES if int(source_breakdown.get(source, 0)) <= 0]
    four_source_coverage_pass = not missing_sources
    blocking = list(errors)
    if "nasa" in missing_sources:
        blocking.append("nasa_coverage_gap")
    elif missing_sources:
        blocking.append("source_coverage_gap")
    production_ready = False
    return {
        "phase": "Phase 85",
        "mode": "four_source_shadow_readiness_eval_gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "package_report": str(package_report),
        "package_integrity_pass": package_integrity_pass,
        "four_source_coverage_pass": four_source_coverage_pass,
        "production_ready": production_ready,
        "blocking_reasons": blocking,
        "missing_sources": missing_sources,
        "counts": {"items": len(items), "triples": len(triples), "narratives": len(narratives)},
        "source_breakdown": source_breakdown,
        "approval_status": manifest.get("approval_status", ""),
        "recommended_next": "nasa_metadata_repair_or_three_source_review_preview",
        "current_summary": "3-source pending package with NASA coverage gap",
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": registry,
    }


def render_md(report: Dict[str, Any]) -> str:
    lines = [
        "# Four-source shadow readiness/eval gate",
        "",
        f"- package_integrity_pass: `{report['package_integrity_pass']}`",
        f"- four_source_coverage_pass: `{report['four_source_coverage_pass']}`",
        f"- production_ready: `{report['production_ready']}`",
        f"- blocking_reasons: `{', '.join(report['blocking_reasons'])}`",
        f"- current_summary: `{report['current_summary']}`",
        "",
        "| source | items |",
        "|---|---:|",
    ]
    for source in REQUIRED_SOURCES:
        lines.append(f"| {source} | {int(report['source_breakdown'].get(source, 0))} |")
    lines.extend(["", "Next: repair NASA metadata coverage or continue as explicitly labeled three-source review preview; do not formally ingest.", ""])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase85 readiness/eval gate for Phase84 pending shadow package.")
    parser.add_argument("--package-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase84" / "four_source_pending_shadow_package_phase84.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase85" / "four_source_shadow_readiness_gate_phase85.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_shadow_readiness_gate_phase85.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase85 or docs/", file=sys.stderr)
        return 2
    report = build_gate(package_report=Path(args.package_report))
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"integrity={report['package_integrity_pass']} coverage={report['four_source_coverage_pass']} production={report['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

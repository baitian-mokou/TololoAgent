from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase88") or (allow_docs and rel.parts[:1] == ("docs",))


def item_ok(row: Dict[str, Any]) -> bool:
    return bool(row.get("source") or row.get("source_id")) and bool(row.get("title") or row.get("subject")) and bool(row.get("source_url") or row.get("entity_id")) and bool(row.get("schema_version")) and isinstance(row.get("quality_flags"), dict) and bool(row.get("provenance"))


def triple_ok(row: Dict[str, Any]) -> bool:
    return all(row.get(k) for k in ("source_id", "subject", "predicate", "object", "schema_version")) and isinstance(row.get("quality_flags"), dict) and bool(row.get("provenance"))


def nasa_repair_quality(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    nasa = [row for row in items if row.get("source") == "nasa" or row.get("source_id") == "nasa"]
    risks = []
    for row in nasa[:5]:
        flags = row.get("quality_flags", {}) if isinstance(row.get("quality_flags"), dict) else {}
        provenance = row.get("provenance", {}) if isinstance(row.get("provenance"), dict) else {}
        if not flags.get("metadata_repaired"):
            risks.append("metadata_repaired_flag_missing")
        if "phase86_rule" not in provenance:
            risks.append("phase86_rule_missing")
    return {
        "sampled": bool(nasa),
        "sample_count": min(len(nasa), 5),
        "repair_source": "title_or_excerpt",
        "risk_count": len(risks),
        "risks": sorted(set(risks)),
    }


def build_gate(*, package_report: Path, root: Path = ROOT) -> Dict[str, Any]:
    report = read_json(package_report)
    manifest = report.get("manifest", {}) if isinstance(report, dict) else {}
    package = report.get("package", {}) if isinstance(report, dict) else {}
    items = package.get("items", []) if isinstance(package.get("items"), list) else []
    triples = package.get("triples_preview", []) if isinstance(package.get("triples_preview"), list) else []
    narratives = package.get("narratives_preview", []) if isinstance(package.get("narratives_preview"), list) else []
    breakdown = manifest.get("source_breakdown", {}) if isinstance(manifest.get("source_breakdown"), dict) else {}
    errors: List[str] = []
    if manifest.get("approval_status") != "pending_review":
        errors.append("approval_status_not_pending_review")
    if manifest.get("production_ready") is not False:
        errors.append("manifest_production_ready_not_false")
    if int(manifest.get("items", -1)) != len(items):
        errors.append("item_count_mismatch")
    if int(manifest.get("triples", -1)) != len(triples):
        errors.append("triple_count_mismatch")
    if int(manifest.get("narratives", -1)) != len(narratives):
        errors.append("narrative_count_mismatch")
    if not manifest.get("provenance_hash"):
        errors.append("missing_provenance_hash")
    if any(not item_ok(row) for row in items):
        errors.append("item_metadata_missing")
    if any(not triple_ok(row) for row in triples):
        errors.append("triple_metadata_missing")
    if any(not item_ok(row) for row in narratives):
        errors.append("narrative_metadata_missing")
    if report.get("integrity", {}).get("errors"):
        errors.append("phase87_integrity_errors_present")
    if report.get("integrity", {}).get("failed_or_unrepaired_included") is not False:
        errors.append("failed_or_unrepaired_included")
    if any(report.get(flag) is not False for flag in ("formal_raw_write", "formal_default_triples_write", "chroma_write", "neo4j_write")):
        errors.append("formal_write_flag_not_false")
    registry = {s: SOURCE_REGISTRY.get(s, "unknown") for s in REQUIRED_SOURCES}
    if ACTIVE_SOURCE != "zh_wikipedia" or registry != {"zh_wikipedia": "active", "nasa": "disabled", "esa": "disabled", "wikidata": "disabled"}:
        errors.append("source_state_changed")
    missing_sources = [source for source in REQUIRED_SOURCES if int(breakdown.get(source, 0)) <= 0]
    quality = nasa_repair_quality(items)
    return {
        "phase": "Phase 88",
        "mode": "four_source_rebuilt_readiness_eval_gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "package_integrity_pass": not errors,
        "four_source_coverage_pass": not missing_sources,
        "production_ready": False,
        "approval_status": manifest.get("approval_status", ""),
        "blocking_reasons": errors,
        "missing_sources": missing_sources,
        "counts": {"items": len(items), "triples": len(triples), "narratives": len(narratives)},
        "source_breakdown": breakdown,
        "nasa_repair_quality": quality,
        "quality_risks": quality["risks"],
        "recommended_next": "review_only_cli_or_shadow_review_preview",
        "not_production_ingest": True,
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
        "# Four-source rebuilt readiness/eval gate",
        "",
        f"- package_integrity_pass: `{report['package_integrity_pass']}`",
        f"- four_source_coverage_pass: `{report['four_source_coverage_pass']}`",
        f"- production_ready: `{report['production_ready']}`",
        f"- approval_status: `{report['approval_status']}`",
        f"- nasa_repair_quality_risks: `{report['nasa_repair_quality']['risk_count']}`",
        "",
        "| source | items |",
        "|---|---:|",
    ]
    for source in REQUIRED_SOURCES:
        lines.append(f"| {source} | {int(report['source_breakdown'].get(source, 0))} |")
    lines.extend(["", "Next: review-only CLI or shadow review preview; not production ingest.", ""])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase88 rebuilt four-source readiness/eval gate.")
    parser.add_argument("--package-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase87" / "four_source_rebuilt_pending_shadow_package_phase87.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase88" / "four_source_rebuilt_readiness_gate_phase88.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_rebuilt_readiness_gate_phase88.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase88 or docs/", file=sys.stderr)
        return 2
    report = build_gate(package_report=Path(args.package_report))
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"integrity={report['package_integrity_pass']} coverage={report['four_source_coverage_pass']} production={report['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

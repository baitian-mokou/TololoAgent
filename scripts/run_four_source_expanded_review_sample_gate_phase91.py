from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase91") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def row_source(row: Dict[str, Any]) -> str:
    return str(row.get("source") or row.get("source_id") or "")


def row_title(row: Dict[str, Any]) -> str:
    return str(row.get("title") or row.get("subject") or row.get("source_id") or "")


def nasa_repair_marker_ok(row: Dict[str, Any]) -> bool:
    metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
    quality = metadata.get("quality_flags", {}) if isinstance(metadata.get("quality_flags"), dict) else {}
    provenance = row.get("provenance", {}) if isinstance(row.get("provenance"), dict) else {}
    return (
        metadata.get("repair_source") == "title_or_excerpt"
        or quality.get("repair_source") == "title_or_excerpt"
        or (quality.get("metadata_repaired") is True and bool(provenance.get("phase86_rule")))
    )


def build_sample(item: Dict[str, Any], triples: List[Dict[str, Any]], narratives: List[Dict[str, Any]]) -> Dict[str, Any]:
    source = row_source(item)
    title = row_title(item)
    item_triples = [t for t in triples if row_source(t) == source and str(t.get("subject", "")) == title]
    item_narratives = [
        n
        for n in narratives
        if row_source(n) == source and (str(n.get("title", "")) == title or str(n.get("subject", "")) == title)
    ]
    return {
        "source": source,
        "title": title,
        "source_url": item.get("source_url") or item.get("entity_id") or "",
        "metadata": {
            "schema_version": item.get("schema_version"),
            "quality_flags": item.get("quality_flags", {}),
            "repair_source": item.get("repair_source"),
        },
        "provenance": item.get("provenance", {}),
        "triples": item_triples[:3],
        "narrative": item_narratives[0] if item_narratives else {},
        "review_status": "pending",
    }


def build_samples(package_report: Path, per_source_limit: int) -> Dict[str, List[Dict[str, Any]]]:
    report = read_json(package_report)
    package = report.get("package", {}) if isinstance(report, dict) else {}
    items = package.get("items", []) if isinstance(package.get("items"), list) else []
    triples = package.get("triples_preview", []) if isinstance(package.get("triples_preview"), list) else []
    narratives = package.get("narratives_preview", []) if isinstance(package.get("narratives_preview"), list) else []
    samples: Dict[str, List[Dict[str, Any]]] = {}
    for source in REQUIRED_SOURCES:
        source_items = [item for item in items if row_source(item) == source][:per_source_limit]
        samples[source] = [build_sample(item, triples, narratives) for item in source_items]
    return samples


def check_quality(samples: Dict[str, List[Dict[str, Any]]]) -> Tuple[List[str], List[str]]:
    findings: List[str] = []
    warnings: List[str] = []
    seen = set()
    if any(source not in samples or not samples.get(source) for source in REQUIRED_SOURCES):
        findings.append("source_balance_missing")
    for source, rows in samples.items():
        for row in rows:
            metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
            quality_flags = metadata.get("quality_flags", {}) if isinstance(metadata.get("quality_flags"), dict) else {}
            key = (source, row.get("title"), row.get("source_url"))
            if key in seen:
                findings.append("duplicate_sample")
            seen.add(key)
            if not all(
                [
                    row.get("source"),
                    row.get("title"),
                    row.get("source_url"),
                    metadata.get("schema_version"),
                    quality_flags,
                    row.get("provenance"),
                    row.get("review_status") == "pending",
                ]
            ):
                findings.append("missing_required_sample_fields")
            if not row.get("triples") or not row.get("narrative"):
                findings.append("sample_missing_triple_or_narrative")
            if source == "nasa" and not nasa_repair_marker_ok(row):
                warnings.append("nasa_repair_marker_missing")
    return sorted(set(findings)), sorted(set(warnings))


def build_report(*, package_report: Path, closure_report: Path, per_source_limit: int = 10) -> Dict[str, Any]:
    samples = build_samples(package_report, per_source_limit)
    findings, warnings = check_quality(samples)
    closure = read_json(closure_report)
    registry = {s: SOURCE_REGISTRY.get(s, "unknown") for s in REQUIRED_SOURCES}
    source_state_ok = ACTIVE_SOURCE == "zh_wikipedia" and registry == {
        "zh_wikipedia": "active",
        "nasa": "disabled",
        "esa": "disabled",
        "wikidata": "disabled",
    }
    if not source_state_ok:
        findings.append("source_state_changed")
    sample_counts = {source: len(rows) for source, rows in samples.items()}
    return {
        "phase": "Phase 91",
        "mode": "expanded_review_sample_quality_gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "samples": samples,
        "sample_counts": sample_counts,
        "total_samples": sum(sample_counts.values()),
        "sample_quality_pass": not findings,
        "blocking_findings": sorted(set(findings)),
        "warnings": warnings,
        "production_ready": False,
        "approval_status": closure.get("approval_status", "pending_review"),
        "closure_verdict": "shadow_review_ready_approval_pending" if not findings else "blocked_for_review",
        "source_risk_notes": ["NASA repaired metadata checked via metadata_repaired plus phase86_rule provenance."],
        "next_recommendations": ["manual review of expanded samples", "larger review-only sample if needed"],
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
        "# Four-source expanded review sample gate",
        "",
        f"- sample_quality_pass: `{report['sample_quality_pass']}`",
        f"- production_ready: `{report['production_ready']}`",
        f"- approval_status: `{report['approval_status']}`",
        f"- closure_verdict: `{report['closure_verdict']}`",
        "",
        "| source | samples |",
        "|---|---:|",
    ]
    for source in REQUIRED_SOURCES:
        lines.append(f"| {source} | {int(report['sample_counts'].get(source, 0))} |")
    lines.extend(["", "Next: manual review of expanded samples; no apply or ingest.", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase91 expanded four-source review sample quality gate.")
    parser.add_argument("--per-source-limit", type=int, default=10)
    parser.add_argument("--package-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase87" / "four_source_rebuilt_pending_shadow_package_phase87.json"))
    parser.add_argument("--closure-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase90" / "four_source_review_sample_quality_closure_phase90.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase91" / "four_source_expanded_review_sample_gate_phase91.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_expanded_review_sample_gate_phase91.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase91 or docs/", file=sys.stderr)
        return 2
    report = build_report(package_report=Path(args.package_report), closure_report=Path(args.closure_report), per_source_limit=args.per_source_limit)
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"samples={report['total_samples']} quality={report['sample_quality_pass']} production={report['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

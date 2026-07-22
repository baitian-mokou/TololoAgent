from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


PACKAGE_SCHEMA = "phase84_pending_shadow_package_v1"


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase84") or (allow_docs and rel.parts[:1] == ("docs",))


def digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def has_meta(row: Dict[str, Any], *, triple: bool = False) -> bool:
    if triple:
        return all(row.get(key) for key in ("source_id", "subject", "predicate", "object", "schema_version")) and bool(row.get("provenance"))
    return bool(row.get("schema_version")) and bool(row.get("provenance")) and bool(row.get("source") or row.get("source_id")) and bool(row.get("source_url") or row.get("entity_id") or row.get("title"))


def dedup_records(records: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], int]:
    seen: set[tuple[str, str, str]] = set()
    out: List[Dict[str, Any]] = []
    dupes = 0
    for row in records:
        key = (str(row.get("source") or row.get("source_id") or ""), str(row.get("source_url") or ""), str(row.get("entity_id") or row.get("title") or row.get("subject") or ""))
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        out.append(row)
    return out, dupes


def build_package(*, phase83_report: Path, root: Path = ROOT) -> Dict[str, Any]:
    phase83 = read_json(phase83_report)
    normalized, item_dupes = dedup_records(list(phase83.get("normalized_records", [])) if isinstance(phase83, dict) else [])
    triples = list(phase83.get("triples_preview", [])) if isinstance(phase83, dict) else []
    narratives = list(phase83.get("narratives_preview", [])) if isinstance(phase83, dict) else []
    rejected = list(phase83.get("rejected_records", [])) if isinstance(phase83, dict) else []
    errors: List[str] = []
    if len(normalized) != int(phase83.get("normalized", len(normalized))):
        errors.append("normalized_count_mismatch")
    if len(triples) != int(phase83.get("triples", len(triples))):
        errors.append("triple_count_mismatch")
    if len(narratives) != int(phase83.get("narratives", len(narratives))):
        errors.append("narrative_count_mismatch")
    if any(not has_meta(row) for row in normalized):
        errors.append("item_metadata_missing")
    if any(not has_meta(row, triple=True) for row in triples):
        errors.append("triple_metadata_missing")
    if any(not has_meta(row) for row in narratives):
        errors.append("narrative_metadata_missing")
    rejected_keys = {(str(row.get("source", "")), str(row.get("title", ""))) for row in rejected}
    package_keys = {(str(row.get("source", "")), str(row.get("title", ""))) for row in normalized}
    if rejected_keys & package_keys:
        errors.append("rejected_record_in_package")
    source_breakdown = dict(sorted(Counter(str(row.get("source") or row.get("source_id")) for row in normalized).items()))
    package_payload = {"items": normalized, "triples_preview": triples, "narratives_preview": narratives}
    manifest = {
        "phase": "Phase 84",
        "schema_version": PACKAGE_SCHEMA,
        "approval_status": "pending_review",
        "items": len(normalized),
        "triples": len(triples),
        "narratives": len(narratives),
        "source_breakdown": source_breakdown,
        "rejected_reference_count": len(rejected),
        "rejected_reference": "evaluation/four_source_expansion/phase83/four_source_shadow_normalize_preview_phase83.json#rejected_records",
        "phase83_report": str(phase83_report),
        "provenance_hash": digest(package_payload),
        "provenance_summary": "Phase84 pending package built only from Phase83 normalized_records/triples_preview/narratives_preview.",
    }
    return {
        "phase": "Phase 84",
        "mode": "four_source_pending_shadow_package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": manifest,
        "package": package_payload,
        "integrity": {
            "errors": errors,
            "item_duplicates_removed": item_dupes,
            "counts_match": not errors,
            "rejected_excluded": "rejected_record_in_package" not in errors,
            "schema_metadata_required": True,
        },
        "source_coverage_gap": {
            "nasa_normalized": source_breakdown.get("nasa", 0),
            "note": "NASA Phase83 rows were rejected by metadata/text quality gate and are not included.",
        },
        "next_recommendation": "readiness_eval_gate",
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def render_md(report: Dict[str, Any]) -> str:
    manifest = report["manifest"]
    lines = [
        "# Four-source pending shadow package",
        "",
        f"- approval_status: `{manifest['approval_status']}`",
        f"- items: `{manifest['items']}`",
        f"- triples: `{manifest['triples']}`",
        f"- narratives: `{manifest['narratives']}`",
        f"- rejected_reference_count: `{manifest['rejected_reference_count']}`",
        f"- integrity_errors: `{len(report['integrity']['errors'])}`",
        "",
        "| source | items |",
        "|---|---:|",
    ]
    for source, count in manifest["source_breakdown"].items():
        lines.append(f"| {source} | {count} |")
    lines.extend(["", "Risk: NASA currently has 0 packaged items because Phase83 rejected NASA preview rows for empty text/claim metadata.", "Next: readiness/eval gate before any approval/apply.", ""])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase84 pending shadow package from Phase83 normalized preview.")
    parser.add_argument("--phase83-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase83" / "four_source_shadow_normalize_preview_phase83.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase84" / "four_source_pending_shadow_package_phase84.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_pending_shadow_package_phase84.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase84 or docs/", file=sys.stderr)
        return 2
    report = build_package(phase83_report=Path(args.phase83_report))
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"items={report['manifest']['items']} triples={report['manifest']['triples']} narratives={report['manifest']['narratives']} errors={len(report['integrity']['errors'])}")
    return 0 if not report["integrity"]["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

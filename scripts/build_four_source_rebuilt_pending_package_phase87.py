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


SCHEMA_VERSION = "phase87_rebuilt_pending_shadow_package_v1"


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase87") or (allow_docs and rel.parts[:1] == ("docs",))


def digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def phase83_items(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(report.get("normalized_records", [])) if isinstance(report.get("normalized_records"), list) else []


def repaired_nasa_items(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = report.get("repaired_candidates", []) if isinstance(report.get("repaired_candidates"), list) else []
    return [row for row in rows if row.get("source") == "nasa" and row.get("source_url") and row.get("title") and row.get("provenance")]


def normalize_repaired(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source": "nasa",
        "source_id": "nasa",
        "title": row["title"],
        "subject": row["title"],
        "source_url": row["source_url"],
        "entity_id": row.get("entity_id", ""),
        "schema_version": SCHEMA_VERSION,
        "extraction_method": "phase86_metadata_repair_preview",
        "confidence": 0.7,
        "quality_flags": {**(row.get("quality_flags") if isinstance(row.get("quality_flags"), dict) else {}), "phase87_rebuilt": True},
        "provenance": {**(row.get("provenance") if isinstance(row.get("provenance"), dict) else {}), "phase87_input": "phase86_repaired_candidates"},
        "text_excerpt": row.get("text_excerpt", ""),
    }


def triples_for(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    base = {
        "source_id": record["source"],
        "subject": record["title"],
        "schema_version": SCHEMA_VERSION,
        "extraction_method": record.get("extraction_method", "phase87_rebuilt_preview"),
        "confidence": record.get("confidence", 0.7),
        "source_url": record.get("source_url", ""),
        "entity_id": record.get("entity_id", ""),
        "validation_status": "accepted_preview",
        "provenance": record.get("provenance", {}),
        "quality_flags": record.get("quality_flags", {}),
    }
    return [
        {**base, "predicate": "SOURCE_URL", "object": record.get("source_url") or record.get("entity_id", "")},
        {**base, "predicate": "HAS_PREVIEW_TEXT", "object": str(record.get("text_excerpt", ""))[:180]},
    ]


def narrative_for(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_id": record["source"],
        "title": record["title"],
        "source_url": record.get("source_url", ""),
        "entity_id": record.get("entity_id", ""),
        "schema_version": SCHEMA_VERSION,
        "extraction_method": record.get("extraction_method", "phase87_rebuilt_preview"),
        "confidence": record.get("confidence", 0.7),
        "quality_flags": record.get("quality_flags", {}),
        "provenance": record.get("provenance", {}),
        "text": record.get("text_excerpt", ""),
    }


def dedup(items: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], int]:
    seen: set[tuple[str, str, str]] = set()
    out: List[Dict[str, Any]] = []
    dupes = 0
    for row in items:
        key = (str(row.get("source", "")), str(row.get("source_url", "")), str(row.get("entity_id") or row.get("title") or ""))
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        out.append(row)
    return out, dupes


def has_meta(row: Dict[str, Any]) -> bool:
    return bool(row.get("source") or row.get("source_id")) and bool(row.get("title") or row.get("subject")) and bool(row.get("source_url") or row.get("entity_id")) and bool(row.get("schema_version")) and bool(row.get("provenance")) and isinstance(row.get("quality_flags"), dict)


def build_package(*, phase83_report: Path, phase86_report: Path, root: Path = ROOT) -> Dict[str, Any]:
    p83 = read_json(phase83_report)
    p86 = read_json(phase86_report)
    base_items = phase83_items(p83 if isinstance(p83, dict) else {})
    nasa_items = [normalize_repaired(row) for row in repaired_nasa_items(p86 if isinstance(p86, dict) else {})]
    items, duplicates = dedup(base_items + nasa_items)
    triples = [triple for item in items for triple in triples_for(item) if triple.get("object")]
    narratives = [narrative_for(item) for item in items]
    breakdown = dict(sorted(Counter(item.get("source") for item in items).items()))
    errors: List[str] = []
    for source in ("zh_wikipedia", "nasa", "esa", "wikidata"):
        if int(breakdown.get(source, 0)) <= 0:
            errors.append(f"missing_{source}")
    if any(not has_meta(item) for item in items):
        errors.append("item_metadata_missing")
    if any(not triple.get("source_id") or not triple.get("subject") or not triple.get("predicate") or not triple.get("object") or not triple.get("provenance") for triple in triples):
        errors.append("triple_metadata_missing")
    failed_or_unrepaired_included = False
    package_payload = {"items": items, "triples_preview": triples, "narratives_preview": narratives}
    manifest = {
        "phase": "Phase 87",
        "schema_version": SCHEMA_VERSION,
        "approval_status": "pending_review",
        "production_ready": False,
        "items": len(items),
        "triples": len(triples),
        "narratives": len(narratives),
        "source_breakdown": breakdown,
        "phase83_items": len(base_items),
        "phase86_nasa_repaired_items": len(nasa_items),
        "provenance_hash": digest(package_payload),
        "provenance_summary": "Phase83 normalized records plus Phase86 NASA repaired/pass candidates only.",
    }
    return {
        "phase": "Phase 87",
        "mode": "four_source_rebuilt_pending_shadow_package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": manifest,
        "package": package_payload,
        "production_ready": False,
        "integrity": {
            "errors": errors,
            "duplicates_removed": duplicates,
            "counts_match": manifest["items"] == len(items) and manifest["triples"] == len(triples) and manifest["narratives"] == len(narratives),
            "failed_or_unrepaired_included": failed_or_unrepaired_included,
            "formal_write_flags_false": True,
        },
        "nasa_repair_evidence": {"phase86_repaired_items": len(nasa_items), "source": str(phase86_report)},
        "remaining_risks": ["pending_review_only", "requires_readiness_eval_gate_before_any_approval"],
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
        "# Four-source rebuilt pending shadow package",
        "",
        f"- approval_status: `{manifest['approval_status']}`",
        f"- production_ready: `{manifest['production_ready']}`",
        f"- items: `{manifest['items']}`",
        f"- triples: `{manifest['triples']}`",
        f"- narratives: `{manifest['narratives']}`",
        f"- integrity_errors: `{len(report['integrity']['errors'])}`",
        "",
        "| source | items |",
        "|---|---:|",
    ]
    for source, count in manifest["source_breakdown"].items():
        lines.append(f"| {source} | {count} |")
    lines.extend(["", "NASA repair evidence: Phase86 repaired/pass candidates are included; Phase82 failed and unrepaired Phase83 rejected rows are not.", "Next: readiness/eval gate.", ""])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase87 rebuilt pending shadow package.")
    parser.add_argument("--phase83-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase83" / "four_source_shadow_normalize_preview_phase83.json"))
    parser.add_argument("--phase86-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase86" / "nasa_metadata_repair_preview_phase86.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase87" / "four_source_rebuilt_pending_shadow_package_phase87.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_rebuilt_pending_shadow_package_phase87.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase87 or docs/", file=sys.stderr)
        return 2
    report = build_package(phase83_report=Path(args.phase83_report), phase86_report=Path(args.phase86_report))
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"items={report['manifest']['items']} triples={report['manifest']['triples']} narratives={report['manifest']['narratives']} errors={len(report['integrity']['errors'])}")
    return 0 if not report["integrity"]["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

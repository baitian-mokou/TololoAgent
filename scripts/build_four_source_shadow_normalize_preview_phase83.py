from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


SCHEMA_VERSION = "phase83_shadow_normalize_preview_v1"


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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase83") or (allow_docs and rel.parts[:1] == ("docs",))


def nonempty(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def succeeded_rows(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = report.get("raw_previews", []) if isinstance(report.get("raw_previews"), list) else []
    return [row for row in rows if row.get("fetched") is True and row.get("status") != "failed"]


def normalize(row: Dict[str, Any]) -> tuple[Dict[str, Any] | None, str]:
    source = nonempty(row.get("source"))
    title = nonempty(row.get("title") or row.get("id"))
    url = nonempty(row.get("url"))
    entity_id = nonempty(row.get("entity_id"))
    text = nonempty(row.get("text_excerpt") or row.get("claims_subset"))
    if not source or not title or not (url or entity_id):
        return None, "missing_source_metadata"
    if not text:
        return None, "empty_text_or_claim"
    return {
        "source": source,
        "source_id": source,
        "title": title,
        "subject": title,
        "source_url": url,
        "entity_id": entity_id,
        "schema_version": SCHEMA_VERSION,
        "extraction_method": "phase83_preview_heuristic",
        "confidence": 0.72 if source in {"nasa", "esa"} else 0.68,
        "quality_flags": {**(row.get("quality_flags") if isinstance(row.get("quality_flags"), dict) else {}), "non_empty_text": True},
        "provenance": {"phase82_status": row.get("status", ""), "phase82_reason": row.get("reason", "")},
        "text_excerpt": text[:900],
    }, ""


def triples_for(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    base = {
        "source_id": record["source"],
        "subject": record["subject"],
        "schema_version": SCHEMA_VERSION,
        "extraction_method": record["extraction_method"],
        "confidence": record["confidence"],
        "source_url": record["source_url"],
        "entity_id": record["entity_id"],
        "validation_status": "accepted_preview",
        "provenance": record["provenance"],
    }
    rows = [
        {**base, "predicate": "SOURCE_URL", "object": record["source_url"] or record["entity_id"]},
        {**base, "predicate": "HAS_PREVIEW_TEXT", "object": record["text_excerpt"][:180]},
    ]
    return [row for row in rows if row["subject"] and row["predicate"] and row["object"]]


def narrative_for(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_id": record["source"],
        "title": record["title"],
        "source_url": record["source_url"],
        "entity_id": record["entity_id"],
        "schema_version": SCHEMA_VERSION,
        "extraction_method": record["extraction_method"],
        "confidence": record["confidence"],
        "quality_flags": record["quality_flags"],
        "provenance": record["provenance"],
        "text": record["text_excerpt"],
    }


def build_report(*, report_path: Path, root: Path = ROOT) -> Dict[str, Any]:
    phase82 = read_json(report_path)
    succeeded = succeeded_rows(phase82 if isinstance(phase82, dict) else {})
    normalized: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    duplicates = 0
    for row in succeeded:
        record, reason = normalize(row)
        if record is None:
            rejected.append({"source": row.get("source", ""), "title": row.get("title", ""), "reason": reason})
            continue
        key = (record["source"], record["source_url"], record["entity_id"] or record["title"].lower())
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        normalized.append(record)
    triples = [triple for record in normalized for triple in triples_for(record)]
    narratives = [narrative_for(record) for record in normalized]
    per_source = Counter(record["source"] for record in normalized)
    return {
        "phase": "Phase 83",
        "mode": "four_source_shadow_normalize_materialize_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_succeeded": len(succeeded),
        "normalized": len(normalized),
        "rejected": len(rejected),
        "duplicates": duplicates,
        "triples": len(triples),
        "narratives": len(narratives),
        "per_source_normalized": dict(sorted(per_source.items())),
        "normalized_records": normalized,
        "triples_preview": triples,
        "narratives_preview": narratives,
        "rejected_records": rejected,
        "quality_flags": {"empty_text_rejected": True, "source_metadata_required": True, "dedup_enabled": True},
        "next_recommendation": "review_phase83_preview_then_build_pending_shadow_packages",
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
    lines = [
        "# Four-source shadow normalize/materialize preview",
        "",
        f"- input_succeeded: `{report['input_succeeded']}`",
        f"- normalized: `{report['normalized']}`",
        f"- rejected: `{report['rejected']}`",
        f"- triples: `{report['triples']}`",
        f"- narratives: `{report['narratives']}`",
        f"- active_source: `{report['active_source']}`",
        "",
        "| source | normalized |",
        "|---|---:|",
    ]
    for source, count in report["per_source_normalized"].items():
        lines.append(f"| {source} | {count} |")
    lines.extend(["", "Boundaries: evaluation/docs only; no default raw/triples, Chroma, Neo4j, source switch, or ingestion cleanup.", ""])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase83 shadow normalize/materialize preview from Phase82 succeeded rows.")
    parser.add_argument("--phase82-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase82" / "four_source_controlled_raw_preview_phase82.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase83" / "four_source_shadow_normalize_preview_phase83.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_shadow_normalize_preview_phase83.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase83 or docs/", file=sys.stderr)
        return 2
    report = build_report(report_path=Path(args.phase82_report))
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"input={report['input_succeeded']} normalized={report['normalized']} rejected={report['rejected']} triples={report['triples']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

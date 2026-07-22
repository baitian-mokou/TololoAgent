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
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase89") or (
        allow_docs and rel.parts[:1] == ("docs",)
    )


def row_source(row: Dict[str, Any]) -> str:
    return str(row.get("source") or row.get("source_id") or "")


def compact_item(item: Dict[str, Any], triples: List[Dict[str, Any]], narratives: List[Dict[str, Any]]) -> Dict[str, Any]:
    source = row_source(item)
    subject = str(item.get("subject") or item.get("title") or item.get("source_id") or "")
    return {
        "source": source,
        "title": item.get("title") or item.get("subject") or "",
        "source_url": item.get("source_url") or item.get("entity_id") or "",
        "metadata": {
            "schema_version": item.get("schema_version"),
            "quality_flags": item.get("quality_flags", {}),
            "repair_source": item.get("quality_flags", {}).get("repair_source")
            if isinstance(item.get("quality_flags"), dict)
            else None,
        },
        "provenance": item.get("provenance", {}),
        "triples": [t for t in triples if row_source(t) == source and t.get("subject") == subject][:2],
        "narratives": [n for n in narratives if row_source(n) == source and (n.get("subject") == subject or n.get("title") == subject)][:1],
        "review_status": "pending",
    }


def build_preview(
    *,
    package_report: Path,
    gate_report: Path,
    limit: int = 3,
    source_filter: str = "",
) -> Dict[str, Any]:
    phase87 = read_json(package_report)
    phase88 = read_json(gate_report)
    package = phase87.get("package", {}) if isinstance(phase87, dict) else {}
    items = package.get("items", []) if isinstance(package.get("items"), list) else []
    triples = package.get("triples_preview", []) if isinstance(package.get("triples_preview"), list) else []
    narratives = package.get("narratives_preview", []) if isinstance(package.get("narratives_preview"), list) else []
    wanted = [source_filter] if source_filter else list(REQUIRED_SOURCES)
    samples: Dict[str, List[Dict[str, Any]]] = {}
    for source in wanted:
        source_items = [item for item in items if row_source(item) == source][: max(0, limit)]
        samples[source] = [compact_item(item, triples, narratives) for item in source_items]
    registry = {s: SOURCE_REGISTRY.get(s, "unknown") for s in REQUIRED_SOURCES}
    return {
        "phase": "Phase 89",
        "mode": "explicit_review_only_shadow_preview_cli",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_only": True,
        "review_status": "pending",
        "production_ready": False,
        "approval_status": phase88.get("approval_status", ""),
        "phase88_gate": {
            "package_integrity_pass": phase88.get("package_integrity_pass") is True,
            "four_source_coverage_pass": phase88.get("four_source_coverage_pass") is True,
            "production_ready": phase88.get("production_ready") is True,
        },
        "sample_counts": {source: len(rows) for source, rows in samples.items()},
        "samples": samples,
        "nasa_repair_marker": "title_or_excerpt",
        "risk_notes": ["review sample only; not production ingest"],
        "recommended_next": "review_gate",
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
        "# Four-source shadow review preview",
        "",
        f"- review_only: `{report['review_only']}`",
        f"- production_ready: `{report['production_ready']}`",
        f"- review_status: `{report['review_status']}`",
        "",
        "| source | samples |",
        "|---|---:|",
    ]
    for source in REQUIRED_SOURCES:
        if source in report["sample_counts"]:
            lines.append(f"| {source} | {report['sample_counts'][source]} |")
    lines.extend(["", "Next: review gate; not production ingest.", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write Phase89 four-source review-only sample preview.")
    parser.add_argument("--source", choices=REQUIRED_SOURCES, default="")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument(
        "--package-report",
        default=str(
            ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase87"
            / "four_source_rebuilt_pending_shadow_package_phase87.json"
        ),
    )
    parser.add_argument(
        "--gate-report",
        default=str(
            ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase88"
            / "four_source_rebuilt_readiness_gate_phase88.json"
        ),
    )
    parser.add_argument(
        "--out-json",
        default=str(
            ROOT
            / "evaluation"
            / "four_source_expansion"
            / "phase89"
            / "four_source_shadow_review_preview_phase89.json"
        ),
    )
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_shadow_review_preview_phase89.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase89 or docs/", file=sys.stderr)
        return 2
    report = build_preview(
        package_report=Path(args.package_report),
        gate_report=Path(args.gate_report),
        limit=args.limit,
        source_filter=args.source,
    )
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"review_only={report['review_only']} samples={report['sample_counts']} production={report['production_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

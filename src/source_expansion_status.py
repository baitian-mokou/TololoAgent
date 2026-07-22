from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

from config import BASE_DIR
from src.source_control import get_active_source, get_source_status


DEFAULT_SOURCES = ("nasa", "esa", "wikidata")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def first_int(*values: Any) -> int:
    for value in values:
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def source_status(source: str, *, base_dir: Path) -> Dict[str, Any]:
    root = Path(base_dir)
    triples_summary = read_json(root / "data" / "triples" / source / "summary.json")
    eval_report = read_json(root / "evaluation" / "source_expansion" / source / f"{source}_report.json")
    preview = read_json(root / "evaluation" / "source_expansion" / source / f"{source}_shadow_materialization_preview.json")
    materialization = read_json(root / "evaluation" / "source_expansion" / source / f"{source}_shadow_materialization_report.json")
    ingestion = read_json(root / "evaluation" / "ingestion" / f"{source}_manifest_ingestion_report.json")
    probe = read_json(root / "evaluation" / "source_expansion" / "shadow_graph_probe_report.json")

    eval_summary = eval_report.get("summary", {}) if isinstance(eval_report.get("summary"), dict) else {}
    eval_manifest = eval_report.get("manifest", {}) if isinstance(eval_report.get("manifest"), dict) else {}
    ingestion_summary = ingestion.get("summary", {}) if isinstance(ingestion.get("summary"), dict) else {}
    selected = preview.get("selected", {}) if isinstance(preview.get("selected"), dict) else {}
    chroma = materialization.get("chroma", {}) if isinstance(materialization.get("chroma"), dict) else {}
    chroma_stats = chroma.get("stats", {}) if isinstance(chroma.get("stats"), dict) else {}
    neo4j = materialization.get("neo4j", {}) if isinstance(materialization.get("neo4j"), dict) else {}
    probe_source = (probe.get("sources", {}) if isinstance(probe.get("sources"), dict) else {}).get(source, {})

    return {
        "source": source,
        "source_status": get_source_status(source),
        "active_source": get_active_source(),
        "raw_count": first_int(
            ingestion_summary.get("fetched"),
            ingestion.get("fetched_count"),
            ingestion.get("fetched"),
            ingestion.get("raw_written"),
        ),
        "triple_count": first_int(triples_summary.get("triples_written"), selected.get("triple_records")),
        "narrative_count": first_int(triples_summary.get("narratives_written"), selected.get("narrative_records")),
        "strict_gate_passed": bool(eval_report.get("gates", {}).get("passed")),
        "strict_query_count": first_int(eval_manifest.get("strict_query_count"), eval_summary.get("total_queries")),
        "exploratory_count": first_int(eval_manifest.get("exploratory_query_count")),
        "exact_accuracy": eval_summary.get("exact_accuracy"),
        "chroma_shadow_count": first_int(chroma_stats.get("total")),
        "chroma_shadow_path": str(chroma.get("persist_dir") or ""),
        "neo4j_last_import_nodes": first_int(neo4j.get("loaded_nodes")),
        "neo4j_last_import_relationships": first_int(neo4j.get("loaded_relationships")),
        "last_probe_status": str(probe_source.get("status") or "missing"),
        "last_probe_node_count": first_int(probe_source.get("node_count")),
        "last_probe_relationship_count": first_int(probe_source.get("relationship_count")),
        "last_probe_relation_type_counts": probe_source.get("relation_type_counts", {})
        if isinstance(probe_source.get("relation_type_counts"), dict)
        else {},
        "last_probe_sample_edges": probe_source.get("sample_edges", [])
        if isinstance(probe_source.get("sample_edges"), list)
        else [],
        "last_probe_contract_checks": probe_source.get("contract_checks", {})
        if isinstance(probe_source.get("contract_checks"), dict)
        else {},
    }


def collect_source_expansion_status(
    *,
    base_dir: Path | str = Path(BASE_DIR),
    sources: Iterable[str] = DEFAULT_SOURCES,
) -> Dict[str, Dict[str, Any]]:
    root = Path(base_dir)
    return {str(source): source_status(str(source), base_dir=root) for source in sources}

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, SOURCE_REGISTRY
from src.source_control import get_source_schema_version


SOURCES = ("nasa", "esa", "wikidata")
DEFAULT_REPORT = ROOT / "evaluation" / "source_expansion" / "shadow_graph_probe_report.json"

PROBE_QUERIES = {
    "counts": (
        "MATCH (a)-[r]->(b) "
        "WHERE coalesce(r.source, '') = $source "
        "WITH collect(DISTINCT a.name) + collect(DISTINCT b.name) AS names, count(r) AS relationship_count "
        "UNWIND names AS name "
        "RETURN count(DISTINCT name) AS node_count, relationship_count"
    ),
    "relation_types": (
        "MATCH ()-[r]->() "
        "WHERE coalesce(r.source, '') = $source "
        "RETURN type(r) AS relation, count(r) AS count "
        "ORDER BY count DESC, relation ASC"
    ),
    "sample_edges": (
        "MATCH (a)-[r]->(b) "
        "WHERE coalesce(r.source, '') = $source "
        "RETURN a.name AS subject, type(r) AS relation, b.name AS object, "
        "coalesce(r.source, '') AS source, coalesce(r.schema_version, '') AS schema_version, "
        "coalesce(r.source_title, '') AS source_title, coalesce(r.source_url, '') AS source_url "
        "ORDER BY relation ASC, subject ASC, object ASC "
        "LIMIT 10"
    ),
    "contract": (
        "MATCH ()-[r]->() "
        "WHERE coalesce(r.source, '') = $source "
        "RETURN "
        "0 AS bad_source_count, "
        "sum(CASE WHEN coalesce(r.source, '') = $source AND "
        "(coalesce(r.source_title, '') = '' OR coalesce(r.origin, '') = '' OR coalesce(r.source_role, '') = '') "
        "THEN 1 ELSE 0 END) AS missing_metadata_count, "
        "sum(CASE WHEN coalesce(r.source, '') = $source AND coalesce(r.schema_version, '') = '' "
        "THEN 1 ELSE 0 END) AS missing_schema_count"
    ),
}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def connect_driver():
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        session.run("RETURN 1").consume()
    return driver


def first(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return dict(rows[0]) if rows else {}


def probe_source(driver, source: str) -> Dict[str, Any]:
    with driver.session() as session:
        counts = first([dict(row) for row in session.run(PROBE_QUERIES["counts"], source=source)])
        relation_rows = [dict(row) for row in session.run(PROBE_QUERIES["relation_types"], source=source)]
        samples = [dict(row) for row in session.run(PROBE_QUERIES["sample_edges"], source=source)]
        contract = first([dict(row) for row in session.run(PROBE_QUERIES["contract"], source=source)])

    bad_source = int(contract.get("bad_source_count") or 0)
    missing_metadata = int(contract.get("missing_metadata_count") or 0)
    missing_schema = int(contract.get("missing_schema_count") or 0)
    schema_version = get_source_schema_version(source)
    sample_schema_mismatch = sum(
        1 for item in samples if item.get("schema_version") and item.get("schema_version") != schema_version
    )
    contract_checks = {
        "passed": bad_source == 0 and missing_metadata == 0 and missing_schema == 0 and sample_schema_mismatch == 0,
        "bad_source_count": bad_source,
        "missing_metadata_count": missing_metadata,
        "missing_schema_count": missing_schema,
        "sample_schema_mismatch_count": sample_schema_mismatch,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry_unchanged": SOURCE_REGISTRY.get("zh_wikipedia") == "active"
        and all(SOURCE_REGISTRY.get(name) == "disabled" for name in SOURCES),
    }
    return {
        "status": "ok",
        "source": source,
        "schema_version": schema_version,
        "node_count": int(counts.get("node_count") or 0),
        "relationship_count": int(counts.get("relationship_count") or 0),
        "relation_type_counts": {str(row.get("relation")): int(row.get("count") or 0) for row in relation_rows},
        "sample_edges": samples,
        "contract_checks": contract_checks,
    }


def build_probe_report(sources: Sequence[str], *, connect: Callable[[], Any] = connect_driver) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "shadow_graph_probe_read_only",
        "active_source": ACTIVE_SOURCE,
        "registry": {name: SOURCE_REGISTRY.get(name) for name in ("zh_wikipedia", *SOURCES)},
        "connection": {"ok": False, "uri": NEO4J_URI, "user": NEO4J_USER},
        "sources": {},
    }
    try:
        driver = connect()
    except Exception as exc:
        report["connection"].update({"ok": False, "error": str(exc)})
        for source in sources:
            report["sources"][source] = {"status": "skipped", "reason": "neo4j_connection_failed"}
        return report

    try:
        report["connection"]["ok"] = True
        for source in sources:
            try:
                report["sources"][source] = probe_source(driver, source)
            except Exception as exc:
                report["sources"][source] = {"status": "failed", "error": str(exc)}
    finally:
        close = getattr(driver, "close", None)
        if callable(close):
            close()
    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Read-only Neo4j shadow namespace probe.")
    parser.add_argument("--source", choices=[*SOURCES, "all"], default="all")
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    sources = list(SOURCES) if args.source == "all" else [args.source]
    report = build_probe_report(sources)
    write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

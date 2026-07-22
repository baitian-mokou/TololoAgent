from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, BASE_DIR, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, TRIPLES_DIR
from src.gui.settings_manager import SettingsManager
from src.knowledge_graph.neo4j_loader import Neo4jLoader
from src.source_control import SOURCE_ROLE, get_source_namespace_dir, get_source_schema_version


BASIC_RELATIONS = {"HAS_MASS", "HAS_RADIUS", "HAS_ATMOSPHERE"}


def _settings_connection() -> Dict[str, str]:
    settings = SettingsManager().get_all()
    conn = settings.get("connect", {})
    return {
        "uri": str(conn.get("neo4j_uri") or "bolt://127.0.0.1:7687"),
        "user": str(conn.get("neo4j_user") or "neo4j"),
        "password": str(conn.get("neo4j_password") or ""),
    }


def _candidate_connections() -> List[Dict[str, str]]:
    settings_conn = _settings_connection()
    candidates = [
        {**settings_conn, "profile": "settings"},
        {
            "uri": os.getenv("NEO4J_URI", NEO4J_URI),
            "user": os.getenv("NEO4J_USER", NEO4J_USER),
            "password": os.getenv("NEO4J_PASSWORD", NEO4J_PASSWORD),
            "profile": "config_or_env",
        },
    ]
    unique = []
    seen = set()
    for item in candidates:
        key = (item["uri"], item["user"], item["password"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _first_working_connection() -> Dict[str, str]:
    from neo4j import GraphDatabase

    failures = []
    for conn in _candidate_connections():
        try:
            driver = GraphDatabase.driver(conn["uri"], auth=(conn["user"], conn["password"]))
            with driver.session() as session:
                session.run("RETURN 1").single()
            driver.close()
            return conn
        except Exception as exc:
            failures.append({"profile": conn["profile"], "error": type(exc).__name__})
    return {
        "uri": "",
        "user": "",
        "password": "",
        "profile": "",
        "failures": failures,
    }


def _dump_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _basic_defaults(loader: Neo4jLoader, triples_dir: str) -> List[dict]:
    triple_files = sorted(glob.glob(os.path.join(triples_dir, "*_triples.json")))
    records = loader._collect_importable_triples(triple_files)
    merged_path = Path(BASE_DIR) / "data" / "presentation_exports" / "solar_system_triples_merged.json"
    if merged_path.exists():
        try:
            merged_records = json.loads(merged_path.read_text(encoding="utf-8"))
        except Exception:
            merged_records = []
        for item in merged_records:
            cleaned = loader._clean_graph_triple(item)
            if cleaned:
                records.append(cleaned)

    defaults = [item for item in records if item.get("relation") in BASIC_RELATIONS]
    unique = {}
    for item in defaults:
        key = (item.get("subject", ""), item.get("relation", ""), item.get("object", ""))
        unique.setdefault(key, item)
    defaults = list(unique.values())
    defaults.sort(key=lambda item: (item.get("subject", ""), item.get("relation", ""), item.get("object", "")))
    return defaults


def _exact_exists(session, triple: dict) -> bool:
    relation = triple["relation"]
    result = session.run(
        f"MATCH (n {{name: $subject}})-[r:{relation}]->(m {{name: $object}}) "
        "WHERE coalesce(r.source, $source_name) = $source_name "
        "RETURN count(r) AS c",
        subject=triple["subject"],
        object=triple["object"],
        source_name=triple.get("source") or triple.get("source_name") or ACTIVE_SOURCE,
    ).single()
    return bool(result and int(result["c"] or 0) > 0)


def _quantity_relation_exists(session, triple: dict) -> bool:
    relation = triple["relation"]
    result = session.run(
        f"MATCH (n {{name: $subject}})-[r:{relation}]->(m) "
        "WHERE coalesce(r.source, $source_name) = $source_name "
        "RETURN count(r) AS c",
        subject=triple["subject"],
        source_name=triple.get("source") or triple.get("source_name") or ACTIVE_SOURCE,
    ).single()
    return bool(result and int(result["c"] or 0) > 0)


def _missing_defaults(loader: Neo4jLoader, defaults: List[dict]) -> Dict[str, Any]:
    missing = []
    mars_mass_before = []
    with loader.driver.session() as session:
        mars_mass_before = [
            dict(row)
            for row in session.run(
                "MATCH (n {name: $subject})-[r:HAS_MASS]->(m) "
                "RETURN n.name AS subject, type(r) AS relation, m.name AS object, "
                "coalesce(r.source, '') AS source, coalesce(r.source_title, '') AS source_title "
                "ORDER BY object",
                subject="火星",
            )
        ]

        for triple in defaults:
            relation = triple.get("relation")
            if relation in {"HAS_MASS", "HAS_RADIUS"}:
                if not _quantity_relation_exists(session, triple):
                    missing.append(triple)
            elif relation == "HAS_ATMOSPHERE":
                if not _exact_exists(session, triple):
                    missing.append(triple)

    return {
        "missing": missing,
        "mars_mass_before": mars_mass_before,
    }


def _mars_mass_after(loader: Neo4jLoader) -> List[dict]:
    with loader.driver.session() as session:
        return [
            dict(row)
            for row in session.run(
                "MATCH (n {name: $subject})-[r:HAS_MASS]->(m) "
                "RETURN n.name AS subject, type(r) AS relation, m.name AS object, "
                "coalesce(r.source, '') AS source, coalesce(r.source_title, '') AS source_title "
                "ORDER BY object",
                subject="火星",
            )
        ]


def repair_basic_parameters(dry_run: bool = False, source_name: str = ACTIVE_SOURCE) -> Dict[str, Any]:
    conn = _first_working_connection()
    if not conn.get("uri"):
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": source_name,
            "connected": False,
            "connection_failures": conn.get("failures", []),
            "error": "Neo4j connection failed",
            "neo4j_written": False,
        }

    loader = Neo4jLoader(
        uri=conn["uri"],
        user=conn["user"],
        password=conn["password"],
        source_name=source_name,
    )
    if not loader.driver:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": source_name,
            "connected": False,
            "error": "Neo4j connection failed",
            "neo4j_written": False,
        }

    triples_dir = get_source_namespace_dir(TRIPLES_DIR, source_name)
    defaults = _basic_defaults(loader, triples_dir)
    missing_state = _missing_defaults(loader, defaults)
    missing = missing_state["missing"]
    nodes = 0
    rels = 0
    if missing and not dry_run:
        nodes, rels = loader._write_triples_to_neo4j(missing)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source_name,
        "connection_profile": conn.get("profile", ""),
        "source_role": SOURCE_ROLE,
        "schema_version": get_source_schema_version(source_name),
        "connected": True,
        "dry_run": dry_run,
        "triples_dir": os.path.relpath(triples_dir, BASE_DIR),
        "checked_default_count": len(defaults),
        "missing_default_count": len(missing),
        "neo4j_written": bool(missing and not dry_run),
        "inserted_nodes_attempted": nodes,
        "inserted_relationships_attempted": rels,
        "mars_mass_before": missing_state["mars_mass_before"],
        "mars_mass_after": _mars_mass_after(loader),
        "missing_defaults": [
            {
                "subject": item.get("subject"),
                "relation": item.get("relation"),
                "object": item.get("object"),
                "source_title": item.get("source_title"),
                "origin": item.get("origin"),
                "pattern": item.get("pattern"),
            }
            for item in missing
        ],
    }
    loader.close()
    return report


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Repair missing Neo4j basic parameter triples from local defaults.")
    parser.add_argument("--dry-run", action="store_true", help="Only report missing defaults; do not write Neo4j.")
    parser.add_argument("--source", default=ACTIVE_SOURCE, help="Source namespace to repair.")
    parser.add_argument(
        "--report",
        default=os.path.join(BASE_DIR, "evaluation", "basic_parameter_repair_report.json"),
        help="Report JSON path.",
    )
    args = parser.parse_args()

    report = repair_basic_parameters(dry_run=args.dry_run, source_name=args.source)
    try:
        _dump_json(Path(args.report), report)
        report["report_write_error"] = None
    except OSError as exc:
        report["report_write_error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("connected") else 2


if __name__ == "__main__":
    raise SystemExit(main())

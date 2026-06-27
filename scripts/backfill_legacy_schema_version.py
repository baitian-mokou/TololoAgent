import argparse
import json
import os
import shutil
import sys
from typing import Any, Dict, Iterable, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import ACTIVE_SOURCE, BASE_DIR


DEFAULT_SCHEMA_VERSION = "2.0"
DEFAULT_TRIPLES_DIR = os.path.join(BASE_DIR, "data", "triples")
DEFAULT_REPORT = os.path.join(BASE_DIR, "evaluation", "maintenance", "legacy_schema_cleanup_report.json")


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def safe_title(item: Dict[str, Any]) -> str:
    for key in ("source_title", "page_title", "subject", "name"):
        value = normalize_text(item.get(key))
        if value:
            return value
    return ""


def backup_file(path: str) -> str:
    backup_path = f"{path}.bak"
    shutil.copy2(path, backup_path)
    return backup_path


def migrate_record(item: Dict[str, Any], schema_version: str, source: str) -> Tuple[Dict[str, Any], bool]:
    updated = dict(item)
    changed = False

    if not normalize_text(updated.get("source")):
        updated["source"] = source
        changed = True
    if not normalize_text(updated.get("source_name")):
        updated["source_name"] = normalize_text(updated.get("source")) or source
        changed = True
    if not normalize_text(updated.get("source_title")):
        title = safe_title(updated)
        if title:
            updated["source_title"] = title
            changed = True
    if not normalize_text(updated.get("schema_version")):
        updated["schema_version"] = schema_version
        changed = True
    if not normalize_text(updated.get("source_role")):
        updated["source_role"] = "primary"
        changed = True
    return updated, changed


def migrate_json_file(path: str, schema_version: str, source: str, apply_changes: bool) -> Dict[str, Any]:
    payload = load_json(path)
    changed = False
    updated_records = 0
    if isinstance(payload, list):
        new_payload = []
        for item in payload:
            if isinstance(item, dict):
                migrated, item_changed = migrate_record(item, schema_version, source)
                changed = changed or item_changed
                updated_records += int(item_changed)
                new_payload.append(migrated)
            else:
                new_payload.append(item)
        payload = new_payload
    elif isinstance(payload, dict):
        if any(key in payload for key in ("source", "source_name", "source_title", "schema_version", "source_role")):
            payload, changed = migrate_record(payload, schema_version, source)
            updated_records = int(changed)

    if changed and apply_changes:
        backup_file(path)
        dump_json(path, payload)

    return {
        "path": path,
        "changed": changed,
        "updated_records": updated_records,
    }


def iter_json_files(base_dir: str) -> Iterable[str]:
    for root, _, files in os.walk(base_dir):
        for name in files:
            if name.endswith(".json"):
                yield os.path.join(root, name)


def migrate_local_files(base_dir: str, schema_version: str, source: str, apply_changes: bool) -> Dict[str, Any]:
    file_reports = []
    changed_files = 0
    changed_records = 0
    for path in iter_json_files(base_dir):
        report = migrate_json_file(path, schema_version, source, apply_changes)
        file_reports.append(report)
        if report["changed"]:
            changed_files += 1
            changed_records += report["updated_records"]
    return {
        "base_dir": base_dir,
        "apply_changes": apply_changes,
        "changed_files": changed_files,
        "changed_records": changed_records,
        "files": file_reports,
    }


def migrate_neo4j(schema_version: str, source: str, apply_changes: bool) -> Dict[str, Any]:
    try:
        from src.knowledge_graph.neo4j_loader import Neo4jLoader
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
            "apply_changes": apply_changes,
        }

    loader = Neo4jLoader()
    if not loader.driver:
        return {
            "available": False,
            "error": "Neo4j driver unavailable",
            "apply_changes": apply_changes,
        }

    node_count = 0
    rel_count = 0
    if apply_changes:
        with loader.driver.session() as session:
            node_count = session.run(
                """
                MATCH (n)
                WHERE coalesce(n.schema_version, '') = ''
                   OR coalesce(n.source, '') = ''
                   OR coalesce(n.source_name, '') = ''
                   OR coalesce(n.source_title, '') = ''
                SET n.schema_version = coalesce(n.schema_version, $schema_version),
                    n.source = coalesce(n.source, $source),
                    n.source_name = coalesce(n.source_name, n.source, $source),
                    n.source_title = coalesce(n.source_title, n.page_title, n.name, ''),
                    n.source_role = coalesce(n.source_role, 'primary')
                RETURN count(n) AS c
                """,
                schema_version=schema_version,
                source=source,
            ).single()["c"]
            rel_count = session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE coalesce(r.schema_version, '') = ''
                   OR coalesce(r.source, '') = ''
                   OR coalesce(r.source_name, '') = ''
                   OR coalesce(r.source_title, '') = ''
                SET r.schema_version = coalesce(r.schema_version, $schema_version),
                    r.source = coalesce(r.source, $source),
                    r.source_name = coalesce(r.source_name, r.source, $source),
                    r.source_title = coalesce(r.source_title, a.name, b.name, ''),
                    r.source_role = coalesce(r.source_role, 'primary')
                RETURN count(r) AS c
                """,
                schema_version=schema_version,
                source=source,
            ).single()["c"]
    loader.close()
    return {
        "available": True,
        "apply_changes": apply_changes,
        "node_updates": node_count,
        "relationship_updates": rel_count,
    }


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Backfill missing legacy schema_version metadata.")
    parser.add_argument("--triples-dir", default=DEFAULT_TRIPLES_DIR, help="Path to data/triples.")
    parser.add_argument("--schema-version", default=DEFAULT_SCHEMA_VERSION, help="Schema version to backfill.")
    parser.add_argument("--source", default=ACTIVE_SOURCE, help="Source name to backfill.")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="Path to write the migration report.")
    parser.add_argument("--apply", action="store_true", help="Write changes instead of dry-run only.")
    parser.add_argument("--skip-neo4j", action="store_true", help="Skip Neo4j migration.")
    args = parser.parse_args()

    local_report = migrate_local_files(args.triples_dir, args.schema_version, args.source, args.apply)
    neo4j_report = None if args.skip_neo4j else migrate_neo4j(args.schema_version, args.source, args.apply)

    report = {
        "schema_version": args.schema_version,
        "source": args.source,
        "apply": args.apply,
        "local_files": local_report,
        "neo4j": neo4j_report,
        "overall_pass": True,
    }
    report["overall_pass"] = (
        local_report["changed_files"] >= 0
        and (neo4j_report is None or neo4j_report.get("available", False) or not args.apply)
    )
    dump_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

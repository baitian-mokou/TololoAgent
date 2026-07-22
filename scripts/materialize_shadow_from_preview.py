from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE
from scripts.preview_shadow_materialization import build_preview_report, read_json, summarize_files, write_json
from src.source_control import get_source_schema_version


DEFAULT_SHADOW_CHROMA_ROOT = ROOT / "data" / "chroma_db_shadow"


def selected_paths_from_preview(preview: Dict[str, Any]) -> List[Path]:
    paths = []
    for item in preview.get("selected", {}).get("files", []):
        path = Path(str(item)).resolve()
        if path.exists() and path.name.endswith(("_triples.json", "_narratives.json")):
            paths.append(path)
    return sorted(dict.fromkeys(paths))


def load_narrative_batches(narrative_files: Sequence[Path]) -> tuple[List[str], List[dict], List[str], int]:
    documents: List[str] = []
    metadatas: List[dict] = []
    ids: List[str] = []
    skipped = 0
    seen_ids = set()
    for path in narrative_files:
        try:
            records = read_json(path)
        except Exception:
            skipped += 1
            continue
        for record in records if isinstance(records, list) else []:
            content = str(record.get("content") or "").strip()
            if len(content) < 10:
                skipped += 1
                continue
            chunk_id = str(record.get("chunk_id") or "").strip()
            if not chunk_id:
                chunk_id = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
            if chunk_id in seen_ids:
                skipped += 1
                continue
            seen_ids.add(chunk_id)
            documents.append(content)
            ids.append(chunk_id)
            metadatas.append({
                "page_title": str(record.get("page_title") or ""),
                "section": str(record.get("section") or ""),
                "source": str(record.get("source_name") or record.get("source") or ""),
                "source_name": str(record.get("source_name") or record.get("source") or ""),
                "source_title": str(record.get("source_title") or ""),
                "origin": str(record.get("origin") or ""),
                "type": str(record.get("type") or ""),
                "source_role": str(record.get("source_role") or ""),
                "schema_version": str(record.get("schema_version") or ""),
            })
    return documents, metadatas, ids, skipped


def write_chroma_shadow(
    source: str,
    narrative_files: Sequence[Path],
    *,
    shadow_chroma_root: Path = DEFAULT_SHADOW_CHROMA_ROOT,
    chroma_store_cls=None,
) -> Dict[str, Any]:
    if chroma_store_cls is None:
        return {"skipped": True, "skipped_reason": "chroma_store_not_configured"}
    persist_dir = shadow_chroma_root / source
    store = chroma_store_cls(persist_dir=str(persist_dir), source_name=source)
    try:
        store.initialize()
        documents, metadatas, ids, skipped_records = load_narrative_batches(narrative_files)
        added = 0
        existing_skipped = 0
        batch_size = 50
        for index in range(0, len(documents), batch_size):
            batch_docs = documents[index:index + batch_size]
            batch_meta = metadatas[index:index + batch_size]
            batch_ids = ids[index:index + batch_size]
            if hasattr(store, "_filter_existing_documents"):
                batch_docs, batch_meta, batch_ids, skipped = store._filter_existing_documents(
                    batch_docs,
                    batch_meta,
                    batch_ids,
                )
                existing_skipped += skipped
            if batch_docs:
                added += store.add_document(batch_docs, metadatas=batch_meta, ids=batch_ids)
        stats = store.get_stats() if hasattr(store, "get_stats") else {}
        return {
            "skipped": False,
            "persist_dir": str(persist_dir),
            "added_narratives": added,
            "existing_skipped": existing_skipped,
            "record_skipped": skipped_records,
            "stats": stats,
        }
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


def write_neo4j_shadow(source: str, triple_files: Sequence[Path], *, neo4j_loader_cls=None) -> Dict[str, Any]:
    if neo4j_loader_cls is None:
        return {"skipped": True, "skipped_reason": "neo4j_loader_not_configured"}
    try:
        loader = neo4j_loader_cls(source_name=source)
    except Exception as exc:
        return {"skipped": True, "skipped_reason": "neo4j_skipped_connection_error", "error": str(exc)}
    try:
        if not getattr(loader, "driver", None):
            return {"skipped": True, "skipped_reason": "neo4j_skipped_connection_unavailable"}
        triples_to_import = loader._collect_importable_triples([str(path) for path in triple_files])
        nodes, relationships = loader._write_triples_to_neo4j(triples_to_import)
        return {
            "skipped": False,
            "selected_triple_files": len(triple_files),
            "importable_triples": len(triples_to_import),
            "loaded_nodes": nodes,
            "loaded_relationships": relationships,
        }
    except Exception as exc:
        return {"skipped": True, "skipped_reason": "neo4j_skipped_import_error", "error": str(exc)}
    finally:
        close = getattr(loader, "close", None)
        if callable(close):
            close()


def materialize_from_preview(
    source: str,
    *,
    preview_path: Optional[Path] = None,
    dry_run: bool = True,
    output_path: Optional[Path] = None,
    shadow_chroma_root: Path = DEFAULT_SHADOW_CHROMA_ROOT,
    chroma_store_cls=None,
    neo4j_loader_cls=None,
) -> Dict[str, Any]:
    source_name = str(source or "").strip().lower()
    if preview_path is None:
        preview = build_preview_report(source_name)
    else:
        preview = read_json(Path(preview_path))
    selected = selected_paths_from_preview(preview)
    triple_files = [path for path in selected if path.name.endswith("_triples.json")]
    narrative_files = [path for path in selected if path.name.endswith("_narratives.json")]

    report: Dict[str, Any] = {
        "source": source_name,
        "source_schema_version": get_source_schema_version(source_name),
        "dry_run": dry_run,
        "mode": "manifest_filtered_shadow_materialization",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_source_before": ACTIVE_SOURCE,
        "active_source_after": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "preview_path": str(preview_path) if preview_path else "",
        "selected": summarize_files(selected),
    }

    if dry_run:
        report["chroma"] = {"skipped": True, "skipped_reason": "dry_run"}
        report["neo4j"] = {"skipped": True, "skipped_reason": "dry_run"}
    else:
        report["chroma"] = write_chroma_shadow(
            source_name,
            narrative_files,
            shadow_chroma_root=shadow_chroma_root,
            chroma_store_cls=chroma_store_cls,
        )
        report["neo4j"] = write_neo4j_shadow(source_name, triple_files, neo4j_loader_cls=neo4j_loader_cls)

    if output_path:
        write_json(Path(output_path), report)
    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Materialize selected shadow artifacts from a preview report.")
    parser.add_argument("--source", choices=["nasa", "esa", "wikidata"], required=True)
    parser.add_argument("--preview-json", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--shadow-chroma-root", default=str(DEFAULT_SHADOW_CHROMA_ROOT))
    parser.add_argument("--apply", action="store_true", help="Write isolated Chroma shadow data and best-effort Neo4j source namespace.")
    args = parser.parse_args()

    from src.knowledge_graph.neo4j_loader import Neo4jLoader
    from src.vector_store.chroma_store import ChromaStore

    output = args.output or ROOT / "evaluation" / "source_expansion" / args.source / f"{args.source}_shadow_materialization_report.json"
    preview_path = Path(args.preview_json) if args.preview_json else ROOT / "evaluation" / "source_expansion" / args.source / f"{args.source}_shadow_materialization_preview.json"
    report = materialize_from_preview(
        args.source,
        preview_path=preview_path,
        dry_run=not args.apply,
        output_path=Path(output),
        shadow_chroma_root=Path(args.shadow_chroma_root),
        chroma_store_cls=ChromaStore,
        neo4j_loader_cls=Neo4jLoader,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

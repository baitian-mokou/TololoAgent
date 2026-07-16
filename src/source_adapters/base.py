from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from config import BASE_DIR, RAW_JSON_DIR, TRIPLES_DIR
from src.source_control import (
    RECORD_TYPE_EMBEDDING_CHUNK,
    RECORD_TYPE_TRIPLE_CANDIDATE,
    SOURCE_ROLE,
    build_record_metadata,
    get_source_namespace_dir,
    get_source_schema_version,
)


REQUIRED_METADATA_FIELDS = (
    "source",
    "source_name",
    "source_role",
    "origin",
    "schema_version",
    "source_title",
)

SOURCE_ADAPTER_MODES = ("offline", "dry-run", "live")


def dump_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_title(title: str) -> str:
    value = str(title or "").strip()
    return re.sub(r'[\\/:*?"<>|？！：；，。、【】「」『』《》（）→←↑↓"\x27\u2019\u0305]', "_", value)


def list_namespace_files(base_dir: str, suffix: str) -> List[str]:
    if not os.path.isdir(base_dir):
        return []
    return sorted(
        os.path.join(base_dir, name)
        for name in os.listdir(base_dir)
        if name.endswith(suffix)
    )


class SourceAdapter:
    """Base class for shadow-only source materialization.

    Adapters emit canonical triples/narratives into the source namespace. They do
    not activate sources or change retrieval defaults.
    """

    source_name = ""
    origin = "api"
    materialization_mode = "offline_fixture"
    cutover_ready = False

    def __init__(
        self,
        *,
        base_dir: str = BASE_DIR,
        raw_json_dir: str = RAW_JSON_DIR,
        triples_dir: str = TRIPLES_DIR,
        graph_loader_cls=None,
        chroma_store_cls=None,
        agent_cls=None,
        mode: str = "offline",
    ):
        if not self.source_name:
            raise ValueError("source_name must be defined by subclasses")
        self.mode = self._normalize_mode(mode)
        self.base_dir = base_dir
        self.raw_root = raw_json_dir
        self.triples_root = triples_dir
        self.raw_dir = get_source_namespace_dir(raw_json_dir, self.source_name)
        self.triples_dir = get_source_namespace_dir(triples_dir, self.source_name)
        self.schema_version = get_source_schema_version(self.source_name)
        self.graph_loader_cls = graph_loader_cls
        self.chroma_store_cls = chroma_store_cls
        self.agent_cls = agent_cls
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.triples_dir, exist_ok=True)

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        normalized = str(mode or "offline").strip().lower()
        if normalized not in SOURCE_ADAPTER_MODES:
            raise ValueError(f"Unsupported source adapter mode '{mode}'. Expected one of {SOURCE_ADAPTER_MODES}.")
        return normalized

    @property
    def writes_official_namespace(self) -> bool:
        return self.mode == "offline"

    def fetch_or_load_raw(self) -> Dict[str, Any]:
        raise NotImplementedError

    def fetch_offline(self) -> Dict[str, Any]:
        return self.fetch_or_load_raw()

    def fetch_live(self) -> Dict[str, Any]:
        raise NotImplementedError(f"{self.source_name} live fetch is not implemented")

    def normalize_records(self, raw_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def emit_triples(self, title: str, triples: Sequence[Dict[str, Any]], *, write: bool = True) -> int:
        if not triples:
            return 0
        payload = [self._with_triple_metadata(title, item) for item in triples]
        if write:
            filename = safe_title(title)
            dump_json(os.path.join(self.triples_dir, f"{filename}_triples.json"), payload)
        return len(payload)

    def emit_narratives(self, title: str, narratives: Sequence[Dict[str, Any]], *, write: bool = True) -> int:
        if not narratives:
            return 0
        payload = [self._with_narrative_metadata(title, index, item) for index, item in enumerate(narratives)]
        if write:
            filename = safe_title(title)
            dump_json(os.path.join(self.triples_dir, f"{filename}_narratives.json"), payload)
        return len(payload)

    def emit_records(self, records: Sequence[Dict[str, Any]], *, write: bool = True) -> Dict[str, Any]:
        triple_count = 0
        narrative_count = 0
        emitted_titles = []
        for record in records:
            title = str(record.get("title") or record.get("source_title") or "").strip()
            if not title:
                continue
            emitted_titles.append(title)
            triple_count += self.emit_triples(title, record.get("triples", []), write=write)
            narrative_count += self.emit_narratives(title, record.get("narratives", []), write=write)

        summary = {
            "total_triples": triple_count,
            "total_narratives": narrative_count,
            "total_files": len(set(emitted_titles)),
            "pipeline": f"{self.source_name}_source_adapter_v1",
            "source_schema_version": self.schema_version,
            "materialization_mode": self.materialization_mode,
            "mode": self.mode,
            "official_namespace_written": bool(write),
            "cutover_ready": self.cutover_ready,
            "time": datetime.now(timezone.utc).isoformat(),
        }
        if write:
            dump_json(os.path.join(self.triples_dir, "summary.json"), summary)
        return summary

    def materialize_graph(self) -> Dict[str, Any]:
        if self.graph_loader_cls is None:
            return {"skipped": True, "reason": "graph_loader_not_configured"}
        loader = self.graph_loader_cls(source_name=self.source_name)
        total_nodes, total_rels = loader.load_all_triples(triples_dir=self.triples_dir)
        stats = loader.get_stats()
        close = getattr(loader, "close", None)
        if callable(close):
            close()
        return {"loaded_nodes": total_nodes, "loaded_relationships": total_rels, "stats": stats}

    def materialize_chroma(self) -> Dict[str, Any]:
        if self.chroma_store_cls is None:
            return {"skipped": True, "reason": "chroma_store_not_configured"}
        store = self.chroma_store_cls(source_name=self.source_name)
        added = store.load_all_narratives(narratives_dir=self.triples_dir, replace_existing=True)
        return {"added_narratives": added, "stats": store.get_stats()}

    def probe(self) -> Dict[str, Any]:
        if self.agent_cls is None:
            return {"skipped": True, "reason": "agent_not_configured"}
        agent = self.agent_cls(source_name=self.source_name)
        graph_probe = agent.search_neo4j_trace(self.default_graph_probe_query(), limit=5, source_filter=[self.source_name])
        narrative_probe = agent.search_chroma(self.default_narrative_probe_query(), top_k=5, source_filter=[self.source_name])
        return {
            "graph_query": self.default_graph_probe_query(),
            "graph_final_source": graph_probe.get("final_source"),
            "graph_final_result_count": len(graph_probe.get("final_result", [])),
            "graph_final_results": graph_probe.get("final_result", []),
            "narrative_query": self.default_narrative_probe_query(),
            "narrative_result_count": len(narrative_probe),
            "narrative_results": narrative_probe,
        }

    def _fetch_for_mode(self) -> Dict[str, Any]:
        if self.mode == "offline":
            return {
                "requested_mode": self.mode,
                "effective_mode": "offline",
                "status": "ok",
                "error": "",
                "payload": self.fetch_offline(),
            }
        try:
            return {
                "requested_mode": self.mode,
                "effective_mode": "live",
                "status": "ok",
                "error": "",
                "payload": self.fetch_live(),
            }
        except Exception as exc:
            fallback_payload = self.fetch_offline()
            return {
                "requested_mode": self.mode,
                "effective_mode": "offline_fallback",
                "status": "fallback",
                "error": str(exc),
                "payload": fallback_payload,
            }

    def build_report(
        self,
        *,
        output_path: str,
        raw_payload: Dict[str, Any],
        records: Sequence[Dict[str, Any]],
        summary: Dict[str, Any],
        metadata_audit: Dict[str, Any],
        graph: Dict[str, Any],
        chroma: Dict[str, Any],
        probes: Dict[str, Any],
        fetch_status: Dict[str, Any],
    ) -> Dict[str, Any]:
        report = {
            "source_name": self.source_name,
            "source_schema_version": self.schema_version,
            "source_role": SOURCE_ROLE,
            "namespace_status": "shadow_only",
            "mode": self.mode,
            "materialization_mode": self.materialization_mode,
            "cutover_ready": self.cutover_ready,
            "raw_dir": self.raw_dir,
            "triples_dir": self.triples_dir,
            "raw_files": list_namespace_files(self.raw_dir, ".json"),
            "triple_files": list_namespace_files(self.triples_dir, "_triples.json"),
            "narrative_files": list_namespace_files(self.triples_dir, "_narratives.json"),
            "pipeline": summary,
            "metadata_contract": metadata_audit,
            "graph": graph,
            "chroma": chroma,
            "probes": probes,
            "fetch": {
                key: value
                for key, value in fetch_status.items()
                if key != "payload"
            },
            "preview": {
                "record_count": len(list(records)),
                "sample_records": list(records)[:5],
                "official_triples_written": self.writes_official_namespace,
                "official_chroma_written": self.writes_official_namespace and not chroma.get("skipped", False),
                "official_neo4j_written": self.writes_official_namespace and not graph.get("skipped", False),
            },
            "readiness_gate": {
                "passed": bool(metadata_audit["passed"]) if self.writes_official_namespace else True,
                "cutover_ready": False,
                "reason": "shadow namespace is auditable; active-source cutover remains disabled",
            },
            "materialization": {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "output_path": output_path,
            },
        }
        report.update(self.extra_report_fields())
        return report

    def materialize(self, output_path: str, mode: Optional[str] = None) -> Dict[str, Any]:
        if mode is not None:
            self.mode = self._normalize_mode(mode)
        fetch_status = self._fetch_for_mode()
        raw_payload = fetch_status["payload"]
        records = self.normalize_records(raw_payload)
        write_official = self.writes_official_namespace
        summary = self.emit_records(records, write=write_official)
        if write_official:
            metadata_audit = self.audit_metadata_contract()
            graph = self.materialize_graph()
            chroma = self.materialize_chroma()
            probes = self.probe()
        else:
            metadata_audit = {
                "passed": True,
                "checked_records": 0,
                "break_count": 0,
                "breaks": [],
                "skipped": True,
                "reason": "preview mode does not write official triples",
            }
            graph = {"skipped": True, "reason": f"{self.mode}_mode_does_not_write_neo4j"}
            chroma = {"skipped": True, "reason": f"{self.mode}_mode_does_not_write_chroma"}
            probes = {"skipped": True, "reason": f"{self.mode}_mode_does_not_probe_materialized_namespace"}
        report = self.build_report(
            output_path=output_path,
            raw_payload=raw_payload,
            records=records,
            summary=summary,
            metadata_audit=metadata_audit,
            graph=graph,
            chroma=chroma,
            probes=probes,
            fetch_status=fetch_status,
        )
        dump_json(output_path, report)
        return report

    def audit_metadata_contract(self) -> Dict[str, Any]:
        checked = 0
        breaks = []
        for path in glob.glob(os.path.join(self.triples_dir, "*_triples.json")) + glob.glob(os.path.join(self.triples_dir, "*_narratives.json")):
            try:
                records = load_json(path)
            except Exception as exc:
                breaks.append({"path": path, "error": str(exc)})
                continue
            for index, record in enumerate(records if isinstance(records, list) else []):
                checked += 1
                missing = [field for field in REQUIRED_METADATA_FIELDS if not str(record.get(field, "")).strip()]
                if record.get("source_name") != self.source_name or record.get("source") != self.source_name:
                    missing.append("source/source_name")
                if record.get("schema_version") != self.schema_version:
                    missing.append("schema_version")
                if missing:
                    breaks.append({"path": path, "index": index, "missing_or_invalid": sorted(set(missing))})
        return {
            "passed": not breaks,
            "checked_records": checked,
            "break_count": len(breaks),
            "breaks": breaks[:20],
        }

    def _with_triple_metadata(self, title: str, item: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(item)
        payload.setdefault("subject", title)
        payload.setdefault("pattern", f"{self.source_name}_adapter")
        payload.setdefault("raw", f"{self.source_name} adapter record: {title} {payload.get('relation', '')} {payload.get('object', '')}")
        payload.update(build_record_metadata(
            payload.get("origin") or self.origin,
            RECORD_TYPE_TRIPLE_CANDIDATE,
            source_name=self.source_name,
            source_title=title,
        ))
        return payload

    def _with_narrative_metadata(self, title: str, index: int, item: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(item)
        payload.setdefault("page_title", title)
        payload.setdefault("section", "概要")
        payload.setdefault("chunk_index", index)
        payload.setdefault("path", payload.get("section", "概要"))
        payload.setdefault("keywords", [title])
        payload.setdefault("chunk_id", f"{self.source_name}_{safe_title(title)}_{index:02d}")
        payload.update(build_record_metadata(
            payload.get("origin") or self.origin,
            RECORD_TYPE_EMBEDDING_CHUNK,
            source_name=self.source_name,
            source_title=title,
        ))
        return payload

    def default_graph_probe_query(self) -> str:
        return "火卫一绕谁公转"

    def default_narrative_probe_query(self) -> str:
        return "火星大气成分"

    def extra_report_fields(self) -> Dict[str, Any]:
        return {}

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import BASE_DIR, RAW_JSON_DIR, TRIPLES_DIR
from src.crawler.spider import TololoCrawler
from src.knowledge_graph.neo4j_loader import Neo4jLoader
from src.source_adapters.base import dump_json, load_json, safe_title
from src.source_adapters.esa import EsaSmokeAdapter
from src.source_adapters.nasa import NASA_FACT_SHEETS, NasaPipelineAdapter
from src.source_adapters.wikidata import WIKIDATA_ENTITY_URL, WikidataFixtureAdapter
from src.source_control import ACTIVE_SOURCE, apply_record_metadata
from src.vector_store.chroma_store import ChromaStore, LocalBGEEmbedder


RAW_SOURCES = ("zh_wikipedia", "wikidata", "nasa", "esa")
EVALUATION_DIR = os.path.join(BASE_DIR, "evaluation", "ingestion")
WIKIDATA_SEEDS = (
    {"entity": "太阳", "qid": "Q525"},
    {"entity": "水星", "qid": "Q308"},
    {"entity": "金星", "qid": "Q313"},
    {"entity": "地球", "qid": "Q2"},
    {"entity": "月球", "qid": "Q405"},
    {"entity": "火星", "qid": "Q111"},
    {"entity": "木星", "qid": "Q319"},
    {"entity": "土星", "qid": "Q193"},
    {"entity": "天王星", "qid": "Q324"},
    {"entity": "海王星", "qid": "Q332"},
    {"entity": "冥王星", "qid": "Q339"},
    {"entity": "谷神星", "qid": "Q596"},
    {"entity": "火卫一", "qid": "Q7547"},
    {"entity": "火卫二", "qid": "Q7548"},
    {"entity": "木卫二", "qid": "Q3143"},
    {"entity": "木卫三", "qid": "Q3169"},
    {"entity": "木卫四", "qid": "Q3134"},
    {"entity": "土卫六", "qid": "Q2565"},
    {"entity": "海卫一", "qid": "Q3359"},
    {"entity": "灶神星", "qid": "Q3030"},
)
NASA_SEEDS = tuple(NASA_FACT_SHEETS.keys())
ESA_MISSION_SEEDS = (
    {
        "title": "JUICE",
        "url": "https://www.esa.int/Science_Exploration/Space_Science/Juice",
        "targets": ["木星", "木卫二", "木卫三", "木卫四"],
    },
    {
        "title": "Rosetta",
        "url": "https://www.esa.int/Science_Exploration/Space_Science/Rosetta",
        "targets": ["彗星"],
    },
    {
        "title": "Gaia",
        "url": "https://www.esa.int/Science_Exploration/Space_Science/Gaia",
        "targets": ["太阳"],
    },
    {
        "title": "Solar Orbiter",
        "url": "https://www.esa.int/Science_Exploration/Space_Science/Solar_Orbiter",
        "targets": ["太阳"],
    },
    {
        "title": "火星快车号",
        "url": "https://www.esa.int/Science_Exploration/Space_Science/Mars_Express",
        "targets": ["火星"],
    },
)
RELATION_RAW_HINTS = {
    "HAS_MASS": "质量",
    "HAS_RADIUS": "半径",
    "HAS_ATMOSPHERE": "大气",
    "ORBITS": "绕行",
    "PART_OF": "属于",
    "LOCATED_IN": "位于",
    "DISCOVERED_BY": "发现者",
}


@dataclass
class ControlledSourceConfig:
    source_name: str
    allowed_domains: Sequence[str]
    seed_items: Sequence[Any]
    timeout: int = 8
    crawl_delay: float = 2.5
    max_depth: int = 1
    warnings: List[str] = field(default_factory=list)


def ensure_raw_source_directories(raw_root: str = RAW_JSON_DIR) -> Dict[str, str]:
    created = {}
    for source_name in RAW_SOURCES:
        path = os.path.join(raw_root, source_name)
        os.makedirs(path, exist_ok=True)
        created[source_name] = path
    return created


def limit_seed_items(seed_items: Iterable[Any], limit: int) -> List[Any]:
    items = list(seed_items or [])
    if limit <= 0:
        return []
    return items[:limit]


def _hostname(url: str) -> str:
    return str(urlparse(str(url or "")).hostname or "").strip().lower()


def is_allowed_source_url(config: ControlledSourceConfig, url: str) -> bool:
    host = _hostname(url)
    if not host:
        return False
    for domain in config.allowed_domains:
        normalized = str(domain or "").strip().lower()
        if host == normalized or host.endswith(f".{normalized}"):
            return True
    return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_raw_dir(raw_root: str, source_name: str) -> str:
    path = os.path.join(raw_root, source_name)
    os.makedirs(path, exist_ok=True)
    return path


def _source_triples_dir(triples_root: str, source_name: str) -> str:
    path = os.path.join(triples_root, source_name)
    os.makedirs(path, exist_ok=True)
    return path


def _load_json_if_exists(path: str) -> Any:
    if not os.path.exists(path):
        return None
    return load_json(path)


def _record_source_url(record: Dict[str, Any]) -> str:
    value = str(record.get("source_url") or "").strip()
    if value:
        return value
    for item in record.get("triples", []):
        triple_url = str(item.get("source_url") or "").strip()
        if triple_url:
            return triple_url
    return ""


def _write_source_raw_payload(raw_root: str, source_name: str, raw_id: str, payload: Dict[str, Any]) -> str:
    filename = f"{safe_title(raw_id or source_name)}.json"
    path = os.path.join(_source_raw_dir(raw_root, source_name), filename)
    dump_json(path, payload)
    return path


def _write_source_triples_record(triples_dir: str, source_name: str, record: Dict[str, Any]) -> Dict[str, int]:
    title = str(record.get("title") or record.get("source_title") or "").strip()
    if not title:
        return {"triples": 0, "narratives": 0}

    triples = []
    for item in record.get("triples", []):
        payload = dict(item)
        relation = str(payload.get("relation", "")).strip()
        object_value = str(payload.get("object", "")).strip()
        source_field = item.get("source_field", "") or item.get("property_id", "") or item.get("table_field", "")
        payload.setdefault("subject", record.get("subject") or title)
        payload.setdefault("source_url", item.get("source_url") or record.get("source_url", ""))
        payload.setdefault("source_field", source_field)
        if not str(payload.get("raw", "")).strip():
            raw_hint = RELATION_RAW_HINTS.get(relation, relation)
            semantic_context = " ".join(part for part in (str(source_field).strip(), raw_hint, object_value) if part)
            payload["raw"] = semantic_context or object_value
        triples.append(
            apply_record_metadata(
                payload,
                "api",
                "triple_candidate",
                source_name=source_name,
                source_title=title,
            )
        )

    narratives = []
    for item in record.get("narratives", []):
        payload = dict(item)
        payload.setdefault("page_title", title)
        narratives.append(
            apply_record_metadata(
                payload,
                "api",
                "embedding_chunk",
                source_name=source_name,
                source_title=title,
            )
        )

    if triples:
        dump_json(os.path.join(triples_dir, f"{safe_title(title)}_triples.json"), triples)
    if narratives:
        dump_json(os.path.join(triples_dir, f"{safe_title(title)}_narratives.json"), narratives)
    return {"triples": len(triples), "narratives": len(narratives)}


def ingest_records_for_source(
    *,
    source_name: str,
    records: Sequence[Dict[str, Any]],
    base_dir: str = BASE_DIR,
    raw_root: str = RAW_JSON_DIR,
    triples_root: str = TRIPLES_DIR,
    evaluation_root: str | None = None,
    materialize_graph: bool = False,
    materialize_chroma: bool = False,
    materialization_details: Dict[str, Any] | None = None,
    warnings: Sequence[str] | None = None,
    errors: Sequence[str] | None = None,
    skipped_urls: Sequence[str] | None = None,
) -> Dict[str, Any]:
    ensure_raw_source_directories(raw_root)
    triples_dir = _source_triples_dir(triples_root, source_name)
    evaluation_dir = evaluation_root or os.path.join(base_dir, "evaluation", "ingestion")
    os.makedirs(evaluation_dir, exist_ok=True)

    raw_written = 0
    triples_written = 0
    narratives_written = 0
    crawled_urls = []

    for index, record in enumerate(records or [], start=1):
        raw_payload = dict(record.get("raw_payload", {}))
        raw_id = str(record.get("raw_id") or record.get("title") or f"{source_name}_{index}").strip()
        _write_source_raw_payload(raw_root, source_name, raw_id, raw_payload)
        raw_written += 1
        if record.get("source_url"):
            crawled_urls.append(str(record.get("source_url")))
        counts = _write_source_triples_record(triples_dir, source_name, record)
        triples_written += counts["triples"]
        narratives_written += counts["narratives"]

    report = {
        "source": source_name,
        "raw_records_written": raw_written,
        "processed_records_written": len(records or []),
        "triples_written": triples_written,
        "narratives_written": narratives_written,
        "graph_written": bool(materialize_graph),
        "chroma_written": bool(materialize_chroma),
        "crawled_urls": crawled_urls,
        "skipped_urls": list(skipped_urls or []),
        "errors": list(errors or []),
        "warnings": list(warnings or []),
        "materialization_details": dict(materialization_details or {}),
        "generated_at": _utc_now(),
    }
    dump_json(os.path.join(evaluation_dir, f"{source_name}_ingestion_report.json"), report)
    return report


def source_config_for(source_name: str) -> ControlledSourceConfig:
    if source_name == "zh_wikipedia":
        crawler = TololoCrawler()
        seed_items = list(crawler.seed_pages)
        return ControlledSourceConfig(
            source_name=source_name,
            allowed_domains=("zh.wikipedia.org",),
            seed_items=seed_items,
            timeout=12,
            crawl_delay=2.5,
            max_depth=1,
        )
    if source_name == "wikidata":
        return ControlledSourceConfig(
            source_name=source_name,
            allowed_domains=("www.wikidata.org", "wikidata.org"),
            seed_items=WIKIDATA_SEEDS,
            timeout=8,
            crawl_delay=1.0,
            max_depth=1,
        )
    if source_name == "nasa":
        return ControlledSourceConfig(
            source_name=source_name,
            allowed_domains=("science.nasa.gov", "nssdc.gsfc.nasa.gov", "solarsystem.nasa.gov"),
            seed_items=NASA_SEEDS,
            timeout=8,
            crawl_delay=1.0,
            max_depth=1,
        )
    if source_name == "esa":
        return ControlledSourceConfig(
            source_name=source_name,
            allowed_domains=("www.esa.int", "esa.int"),
            seed_items=ESA_MISSION_SEEDS,
            timeout=8,
            crawl_delay=1.0,
            max_depth=1,
        )
    raise KeyError(f"Unsupported source: {source_name}")


def _triples_items_from_payload(payload: Any) -> List[Dict[str, Any]]:
    items = payload if isinstance(payload, list) else []
    triples = []
    for item in items:
        relation = str(item.get("relation", "")).strip()
        obj = str(item.get("object", "")).strip()
        if relation and obj:
            triples.append(
                {
                    "subject": item.get("subject", ""),
                    "relation": relation,
                    "object": obj,
                    "source_url": item.get("source_url", ""),
                    "source_field": item.get("source_field", ""),
                }
            )
    return triples


def _narratives_items_from_payload(payload: Any) -> List[Dict[str, Any]]:
    items = payload if isinstance(payload, list) else []
    narratives = []
    for item in items:
        content = str(item.get("content", "")).strip()
        if content:
            narratives.append(
                {
                    "section": item.get("section", ""),
                    "content": content,
                    "keywords": item.get("keywords", []),
                }
            )
    return narratives


def _zh_seed_payload(seed: Dict[str, Any], *, mode: str, warnings: List[str]) -> Dict[str, Any] | None:
    title = str(seed.get("title") or "").strip()
    category = str(seed.get("category") or "Auto").strip()
    safe = TololoCrawler.sanitize_filename(title)
    existing_path = os.path.join(RAW_JSON_DIR, f"{safe}_html.json")
    payload = _load_json_if_exists(existing_path)
    if payload:
        return payload
    if mode == "offline":
        warnings.append(f"zh_wikipedia offline raw missing for {title}")
        return None
    crawler = TololoCrawler()
    content = crawler.get_page_content(title)
    if not content:
        warnings.append(f"zh_wikipedia live fetch unavailable for {title}")
        return None
    raw_text = str(content.get("raw_text") or "")
    return {
        "title": title,
        "category": category,
        "url": f"{crawler.base_url}/wiki/{title}",
        "html": content.get("html", ""),
        "raw_text": raw_text,
        "content_length": len(raw_text),
        "word_count_cn": content.get("word_count_cn", 0),
        "char_count": len(raw_text),
        "text": raw_text,
        "source": ACTIVE_SOURCE,
        "source_role": "primary",
        "origin": content.get("origin", "api"),
        "fetch_source": content.get("fetch_source", "mediawiki_api"),
        "discovery_origin": "seed",
        "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _build_zh_records(limit: int, mode: str) -> tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    config = source_config_for("zh_wikipedia")
    warnings: List[str] = []
    errors: List[str] = []
    skipped_urls: List[str] = []
    records: List[Dict[str, Any]] = []

    for seed in limit_seed_items(config.seed_items, limit):
        payload = _zh_seed_payload(seed, mode=mode, warnings=warnings)
        if not payload:
            continue
        source_url = str(payload.get("url") or "")
        if not is_allowed_source_url(config, source_url):
            skipped_urls.append(source_url)
            continue
        title = str(payload.get("title") or "").strip()
        safe = safe_title(title)
        triples = _triples_items_from_payload(_load_json_if_exists(os.path.join(TRIPLES_DIR, f"{safe}_triples.json")))
        narratives = _narratives_items_from_payload(_load_json_if_exists(os.path.join(TRIPLES_DIR, f"{safe}_narratives.json")))
        if not narratives and str(payload.get("raw_text") or "").strip():
            narratives = [{
                "section": str(payload.get("category") or "概述"),
                "content": str(payload.get("raw_text") or "")[:400],
                "keywords": [title, "中文维基", "太阳系"],
            }]
        records.append(
            {
                "raw_id": title,
                "raw_payload": payload,
                "title": title,
                "triples": triples,
                "narratives": narratives,
                "source_url": source_url,
            }
        )
    return records, warnings, errors, skipped_urls


def _build_wikidata_records(limit: int, mode: str) -> tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    config = source_config_for("wikidata")
    warnings: List[str] = []
    errors: List[str] = []
    skipped_urls: List[str] = []
    records: List[Dict[str, Any]] = []
    seeds = limit_seed_items(config.seed_items, limit)
    fixture_path = os.path.join(RAW_JSON_DIR, "wikidata", "solar_system_fixture.json")
    fixture_payload = load_json(fixture_path) if os.path.exists(fixture_path) else {"records": []}
    fixture_by_title = {
        str(item.get("title") or "").strip(): item
        for item in fixture_payload.get("records", [])
        if str(item.get("title") or "").strip()
    }

    for seed in seeds:
        title = str(seed.get("entity") or "").strip()
        qid = str(seed.get("qid") or "").strip()
        source_url = WIKIDATA_ENTITY_URL.format(qid=qid) if qid else ""
        if source_url and not is_allowed_source_url(config, source_url):
            skipped_urls.append(source_url)
            continue
        record = None
        raw_payload = None
        if mode == "live":
            try:
                adapter = WikidataFixtureAdapter(entity=qid or title, timeout=config.timeout)
                raw_payload = adapter.fetch_live()
                normalized = adapter.normalize_records(raw_payload)
                record = next((item for item in normalized if str(item.get("title") or "").strip() == title), normalized[0] if normalized else None)
            except Exception as exc:
                warnings.append(f"wikidata live fallback for {title}: {exc}")
        if record is None:
            record = fixture_by_title.get(title)
            raw_payload = {"record": record, "fixture_source": os.path.basename(fixture_path)} if record else None
        if not record:
            errors.append(f"wikidata record missing for {title}")
            continue
        records.append(
            {
                "raw_id": qid or title,
                "raw_payload": dict(raw_payload or {"record": record}),
                "title": str(record.get("title") or title),
                "triples": list(record.get("triples", [])),
                "narratives": list(record.get("narratives", [])),
                "source_url": source_url or _record_source_url(record),
            }
        )
    return records, warnings, errors, skipped_urls


def _build_nasa_records(limit: int, mode: str) -> tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    config = source_config_for("nasa")
    warnings: List[str] = []
    errors: List[str] = []
    skipped_urls: List[str] = []
    records: List[Dict[str, Any]] = []
    adapter = NasaPipelineAdapter(timeout=config.timeout)

    if mode == "live":
        for entity in limit_seed_items(config.seed_items, limit):
            if entity not in NASA_FACT_SHEETS:
                continue
            live_adapter = NasaPipelineAdapter(entity=entity, timeout=config.timeout)
            try:
                raw_payload = live_adapter.fetch_live()
                record = live_adapter._record_from_fact_sheet(raw_payload)
                source_url = str(raw_payload.get("source_url") or "")
                if source_url and is_allowed_source_url(config, source_url):
                    records.append(
                        {
                            "raw_id": str(raw_payload.get("source_record_id") or entity),
                            "raw_payload": raw_payload,
                            "title": str(record.get("title") or entity),
                            "triples": list(record.get("triples", [])),
                            "narratives": list(record.get("narratives", [])),
                            "source_url": source_url,
                        }
                    )
                    if len(records) >= limit:
                        return records[:limit], warnings, errors, skipped_urls
                else:
                    skipped_urls.append(source_url)
            except Exception as exc:
                warnings.append(f"nasa live fallback for {entity}: {exc}")
                break

    raw_files = sorted(Path(adapter.raw_dir).glob("*_html.json"))
    for raw_path in raw_files[: max(limit - len(records), 0)]:
        payload = load_json(str(raw_path))
        source_url = str(payload.get("url") or NASA_FACT_SHEETS.get(str(payload.get("title") or ""), {}).get("url") or "")
        if source_url and not is_allowed_source_url(config, source_url):
            skipped_urls.append(source_url)
            continue
        record = adapter._record_from_offline_raw(payload, str(payload.get("crawl_time") or ""))
        records.append(
            {
                "raw_id": raw_path.stem,
                "raw_payload": payload,
                "title": str(record.get("title") or payload.get("title") or raw_path.stem),
                "triples": list(record.get("triples", [])),
                "narratives": list(record.get("narratives", [])),
                "source_url": source_url,
            }
        )
        if len(records) >= limit:
            break

    if not records:
        errors.append("nasa raw records unavailable")
    return records[:limit], warnings, errors, skipped_urls


def _build_esa_live_record(seed: Dict[str, Any], timeout: int) -> Dict[str, Any] | None:
    import re
    import urllib.request

    title = str(seed.get("title") or "").strip()
    url = str(seed.get("url") or "").strip()
    request = urllib.request.Request(url, headers={"User-Agent": "tololo-controlled-ingestion/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        html = response.read().decode("utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    triples = [{"relation": "OPERATED_BY", "object": "ESA", "source_url": url, "source_field": "live_page"}]
    for target in seed.get("targets", []):
        triples.append({"relation": "HAS_MISSION_TARGET", "object": target, "source_url": url, "source_field": "live_page"})
    return {
        "raw_id": title,
        "raw_payload": {"title": title, "url": url, "html_excerpt": html[:4000]},
        "title": title,
        "triples": triples,
        "narratives": [{
            "section": "任务",
            "content": text[:500],
            "keywords": [title, "ESA", "太阳系任务"],
        }],
        "source_url": url,
    }


def _build_esa_records(limit: int, mode: str) -> tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    config = source_config_for("esa")
    warnings: List[str] = []
    errors: List[str] = []
    skipped_urls: List[str] = []
    records: List[Dict[str, Any]] = []
    fixture_path = os.path.join(RAW_JSON_DIR, "esa", "smoke_fixture.json")
    fixture_payload = load_json(fixture_path) if os.path.exists(fixture_path) else {"records": []}
    fixture_by_title = {
        str(item.get("title") or "").strip(): item
        for item in fixture_payload.get("records", [])
        if str(item.get("title") or "").strip()
    }

    for seed in limit_seed_items(config.seed_items, limit):
        title = str(seed.get("title") or "").strip()
        url = str(seed.get("url") or "").strip()
        if url and not is_allowed_source_url(config, url):
            skipped_urls.append(url)
            continue
        record = None
        if mode == "live":
            try:
                record = _build_esa_live_record(seed, config.timeout)
            except Exception as exc:
                warnings.append(f"esa live fallback for {title}: {exc}")
        if record is None:
            fixture_record = fixture_by_title.get(title)
            if not fixture_record:
                errors.append(f"esa record missing for {title}")
                continue
            record = {
                "raw_id": title,
                "raw_payload": {"record": fixture_record, "fixture_source": os.path.basename(fixture_path)},
                "title": title,
                "triples": list(fixture_record.get("triples", [])),
                "narratives": list(fixture_record.get("narratives", [])),
                "source_url": url,
            }
        records.append(record)
    return records[:limit], warnings, errors, skipped_urls


def collect_records_for_source(source_name: str, limit: int, mode: str = "auto") -> tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    effective_mode = "offline" if mode == "auto" else mode
    if source_name == "zh_wikipedia":
        return _build_zh_records(limit, effective_mode)
    if source_name == "wikidata":
        return _build_wikidata_records(limit, effective_mode)
    if source_name == "nasa":
        return _build_nasa_records(limit, effective_mode)
    if source_name == "esa":
        return _build_esa_records(limit, effective_mode)
    raise KeyError(f"Unsupported source: {source_name}")


def _can_materialize_chroma() -> bool:
    probe = LocalBGEEmbedder(cache_root=os.path.join(BASE_DIR, "models", "embedding"))
    try:
        return probe._has_local_model()
    except Exception:
        return False


def _materialize_shadow_namespace(source_name: str, triples_dir: str) -> tuple[bool, bool, Dict[str, Any], List[str], List[str]]:
    warnings: List[str] = []
    errors: List[str] = []
    details: Dict[str, Any] = {
        "graph": {"skipped": True, "reason": "not_attempted"},
        "chroma": {"skipped": True, "reason": "not_attempted"},
    }
    graph_written = False
    chroma_written = False

    if source_name == ACTIVE_SOURCE:
        warnings.append("active source materialization skipped to avoid overwriting the formal namespace")
        details["graph"] = {"skipped": True, "reason": "active_source_boundary"}
        details["chroma"] = {"skipped": True, "reason": "active_source_boundary"}
        return graph_written, chroma_written, details, warnings, errors

    try:
        loader = Neo4jLoader(source_name=source_name)
        if loader.driver is None:
            warnings.append(f"{source_name} graph materialization skipped because Neo4j is not connected")
            details["graph"] = {"skipped": True, "reason": "neo4j_not_connected"}
        else:
            nodes, rels = loader.load_all_triples(triples_dir=triples_dir)
            details["graph"] = {"loaded_nodes": nodes, "loaded_relationships": rels, "stats": loader.get_stats()}
            graph_written = True
        loader.close()
    except Exception as exc:
        warnings.append(f"{source_name} graph materialization skipped: {exc}")
        details["graph"] = {"skipped": True, "reason": str(exc)}

    if not _can_materialize_chroma():
        warnings.append(f"{source_name} chroma materialization skipped because the local embedding model cache is unavailable")
        details["chroma"] = {"skipped": True, "reason": "embedding_model_cache_missing"}
        return graph_written, chroma_written, details, warnings, errors

    try:
        store = ChromaStore(source_name=source_name)
        added = store.load_all_narratives(narratives_dir=triples_dir, replace_existing=True)
        details["chroma"] = {"added_narratives": added, "stats": store.get_stats()}
        chroma_written = True
    except Exception as exc:
        warnings.append(f"{source_name} chroma materialization skipped: {exc}")
        details["chroma"] = {"skipped": True, "reason": str(exc)}

    return graph_written, chroma_written, details, warnings, errors


def run_controlled_ingestion(
    source_name: str,
    *,
    limit: int = 20,
    mode: str = "auto",
) -> Dict[str, Any]:
    ensure_raw_source_directories(RAW_JSON_DIR)
    os.makedirs(EVALUATION_DIR, exist_ok=True)

    records, warnings, errors, skipped_urls = collect_records_for_source(source_name, limit, mode=mode)
    triples_dir = _source_triples_dir(TRIPLES_DIR, source_name)
    report = ingest_records_for_source(
        source_name=source_name,
        records=records,
        base_dir=BASE_DIR,
        raw_root=RAW_JSON_DIR,
        triples_root=TRIPLES_DIR,
        evaluation_root=EVALUATION_DIR,
        materialize_graph=False,
        materialize_chroma=False,
        materialization_details={},
        warnings=warnings,
        errors=errors,
        skipped_urls=skipped_urls,
    )
    graph_written, chroma_written, details, extra_warnings, extra_errors = _materialize_shadow_namespace(source_name, triples_dir)
    report["graph_written"] = graph_written
    report["chroma_written"] = chroma_written
    report["materialization_details"] = details
    report["warnings"] = list(report.get("warnings", [])) + list(extra_warnings)
    report["errors"] = list(report.get("errors", [])) + list(extra_errors)
    dump_json(os.path.join(EVALUATION_DIR, f"{source_name}_ingestion_report.json"), report)
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Controlled solar-system source ingestion entrypoint.")
    parser.add_argument("--source", required=True, choices=tuple(RAW_SOURCES) + ("all",))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--mode", choices=("auto", "offline", "live"), default="auto")
    args = parser.parse_args()

    sources = list(RAW_SOURCES) if args.source == "all" else [args.source]
    reports = [run_controlled_ingestion(source_name, limit=args.limit, mode=args.mode) for source_name in sources]
    print(json.dumps({"sources": sources, "reports": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

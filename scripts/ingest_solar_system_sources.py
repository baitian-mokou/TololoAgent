from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Sequence
from urllib.parse import urldefrag, urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import BASE_DIR, RAW_JSON_DIR, TRIPLES_DIR
from src.crawler.spider import TololoCrawler
from src.knowledge_graph.neo4j_loader import Neo4jLoader
from src.source_adapters.base import dump_json, load_json, safe_title
from src.source_adapters.esa import EsaSmokeAdapter
from src.source_adapters.nasa import (
    NASA_FACT_SHEETS,
    NASA_MARS_STRICT_TABLE_FALLBACK_HTML,
    NasaPipelineAdapter,
    has_strict_fact_sheet_fields,
    html_to_text,
)
from src.source_adapters.wikidata import PROPERTY_RELATION_MAP, WIKIDATA_ENTITY_URL, WikidataFixtureAdapter
from src.source_control import ACTIVE_SOURCE, SOURCE_ROLE, apply_record_metadata, get_source_schema_version
from src.nlp.preprocess import WikiPreprocessor
from src.vector_store.chroma_store import ChromaStore, LocalBGEEmbedder


RAW_SOURCES = ("zh_wikipedia", "wikidata", "nasa", "esa")
EVALUATION_DIR = os.path.join(BASE_DIR, "evaluation", "ingestion")
CHROMA_DB_DIR = os.path.join(BASE_DIR, "data", "chroma_db")
SOURCE_FIXTURES_DIR = os.path.join(BASE_DIR, "data", "source_fixtures")
DISCOVERY_STATE_FILENAME = "__crawl_state__.json"
IGNORED_SOURCE_RAW_FILENAMES = {DISCOVERY_STATE_FILENAME, "solar_system_fixture.json", "smoke_fixture.json", "discovery_fixture.json"}
COLLECTION_CONTEXT: Dict[str, Dict[str, Any]] = {}
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
NASA_DISCOVERY_SEED_URLS = (
    "https://nssdc.gsfc.nasa.gov/planetary/factsheet/",
    "https://science.nasa.gov/solar-system/",
    "https://science.nasa.gov/solar-system/planets/",
    "https://solarsystem.nasa.gov/planets/overview/",
    "https://solarsystem.nasa.gov/moons/overview/",
)
NASA_TITLE_HINTS = {
    "sun": "太阳",
    "mercury": "水星",
    "venus": "金星",
    "earth": "地球",
    "moon": "月球",
    "mars": "火星",
    "jupiter": "木星",
    "saturn": "土星",
    "uranus": "天王星",
    "neptune": "海王星",
    "pluto": "冥王星",
    "ceres": "谷神星",
    "phobos": "火卫一",
    "deimos": "火卫二",
    "europa": "木卫二",
    "ganymede": "木卫三",
    "callisto": "木卫四",
    "titan": "土卫六",
    "triton": "海卫一",
    "vesta": "灶神星",
}
NASA_DISCOVERY_KEYWORDS = tuple(NASA_TITLE_HINTS.keys()) + (
    "factsheet",
    "planetary",
    "solar-system",
    "planets",
    "moons",
    "dwarf-planet",
)
NASA_SKIP_PATH_KEYWORDS = (
    "/news/",
    "/image/",
    "/images/",
    "/gallery/",
    "/video/",
    "/videos/",
    "/podcast/",
    "/feature/",
    "/features/",
    "/events/",
    "/missions/",
    "/mission/",
    "/people/",
    "/playing-the-moon-game",
)
NASA_HIGH_VALUE_PATH_SEGMENTS = (
    "factsheet",
    "overview",
    "in-depth",
    "planet",
    "planets",
    "moon",
    "moons",
    "dwarf-planets",
    "asteroids",
    "comets",
)
NASA_GENERIC_LANDING_SEGMENTS = {
    "solar-system",
    "planets",
    "planet",
    "moons",
    "moon",
    "dwarf-planets",
    "asteroids",
    "comets",
    "asteroids-comets-and-meteors",
    "overview",
    "facts",
    "resources",
}
NASA_NOISE_TITLE_KEYWORDS = (
    "10 things",
    "movie night",
    "multimedia",
    "resources",
    "analog",
    "analogs",
    "planetary analogs",
    "what's that",
    "whats that",
    "photojournal",
    "podcast",
    "playing the moon game",
)
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
ESA_DISCOVERY_SEED_URLS = (
    "https://www.esa.int/Science_Exploration/Space_Science",
    "https://www.esa.int/Enabling_Support/Operations",
)
ESA_TARGET_HINTS = {
    "juice": ["木星", "木卫二", "木卫三", "木卫四"],
    "jupiter": ["木星"],
    "rosetta": ["彗星"],
    "gaia": ["太阳"],
    "solar_orbiter": ["太阳"],
    "solar orbiter": ["太阳"],
    "bepicolombo": ["水星"],
    "mars_express": ["火星"],
    "mars express": ["火星"],
    "venus_express": ["金星"],
    "venus express": ["金星"],
    "smart-1": ["月球"],
    "moon": ["月球"],
    "mercury": ["水星"],
    "mars": ["火星"],
    "venus": ["金星"],
    "comet": ["彗星"],
}
ESA_SKIP_PATH_KEYWORDS = (
    "/news/",
    "/gallery/",
    "/images/",
    "/video/",
    "/videos/",
    "/mediakit/",
    "/Kids/",
    "/Space_in_Member_States/",
)
ESA_PRIMARY_HOSTS = {"www.esa.int", "esa.int"}
ESA_HIGH_VALUE_TITLE_KEYWORDS = (
    "juice",
    "rosetta",
    "gaia",
    "solar orbiter",
    "solar_orbiter",
    "mars express",
    "mars_express",
    "venus express",
    "venus_express",
    "smart-1",
    "bepicolombo",
    "facts about",
    "jupiter",
    "mercury",
    "mars",
    "comet",
)
ESA_NOISE_TITLE_KEYWORDS = (
    "image",
    "images",
    "photo",
    "video",
    "journal",
    "archive",
    "blog",
    "hidden in plain sight",
    "flaps its wings",
    "creeps across",
    "counting craters",
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


def _set_collection_context(source_name: str, **fields: Any) -> None:
    context = COLLECTION_CONTEXT.setdefault(source_name, {})
    for key, value in fields.items():
        if value is not None:
            context[key] = value


def _consume_collection_context(source_name: str) -> Dict[str, Any]:
    return dict(COLLECTION_CONTEXT.pop(source_name, {}))


@dataclass
class ControlledSourceConfig:
    source_name: str
    allowed_domains: Sequence[str]
    seed_items: Sequence[Any]
    timeout: int = 8
    crawl_delay: float = 2.5
    max_depth: int = 1
    max_discovery_fetch_pages: int = 0
    max_candidate_pages: int = 0
    warnings: List[str] = field(default_factory=list)


@dataclass
class DiscoveredHtmlPage:
    url: str
    html: str
    depth: int
    title: str = ""


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


def _normalize_url(url: str, base_url: str = "") -> str:
    resolved = urljoin(base_url, str(url or "").strip())
    clean, _ = urldefrag(resolved)
    return clean.strip()


def _fetch_html(url: str, timeout: int) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "tololo-controlled-ingestion/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _extract_html_links(html: str, base_url: str) -> List[str]:
    links = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', str(html or ""), flags=re.IGNORECASE):
        normalized = _normalize_url(href, base_url)
        if normalized:
            links.append(normalized)
    return links


def _extract_html_title(html: str, fallback: str = "") -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", str(html or ""), flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return fallback
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or fallback


def _sleep_crawl_delay(delay: float) -> None:
    if delay > 0:
        time.sleep(delay)


def _path_looks_binary(path: str) -> bool:
    lowered = str(path or "").lower()
    return lowered.endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".pdf", ".zip", ".xml", ".rss"))


def _discover_html_pages_bfs(
    *,
    config: ControlledSourceConfig,
    seed_urls: Sequence[str],
    timeout: int,
    crawl_delay: float,
    max_depth: int,
    max_fetch_pages: int,
    warnings: List[str],
    should_expand: Callable[[ControlledSourceConfig, str], bool],
    is_candidate: Callable[[ControlledSourceConfig, str], bool],
) -> tuple[List[DiscoveredHtmlPage], List[DiscoveredHtmlPage]]:
    state = _load_source_state(config.source_name)
    queue = deque()
    visited = set(str(url).strip() for url in state.get("visited_urls", []) if str(url).strip())
    fetched_pages: List[DiscoveredHtmlPage] = []
    candidate_pages: List[DiscoveredHtmlPage] = []

    if state.get("pending_queue"):
        warnings.append(
            f"{config.source_name} resuming discovery from checkpoint: visited={len(visited)}, pending={len(state.get('pending_queue', []))}"
        )

    for item in state.get("pending_queue", []):
        url = _normalize_url(str(item.get("url") or "").strip())
        depth = int(item.get("depth", 0) or 0)
        if url and url not in visited:
            queue.append((url, depth))

    for seed_url in seed_urls:
        normalized = _normalize_url(seed_url)
        if normalized and normalized not in visited:
            queue.append((normalized, 0))

    candidate_budget = max(int(getattr(config, "max_candidate_pages", 0) or 0), 0)
    while queue and len(fetched_pages) < max(int(max_fetch_pages or 0), 1):
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        if not should_expand(config, url):
            continue
        try:
            html = _fetch_html(url, timeout)
        except Exception as exc:
            warnings.append(f"{config.source_name} discovery fetch unavailable for {url}: {exc}")
            continue
        page = DiscoveredHtmlPage(
            url=url,
            html=html,
            depth=depth,
            title=_extract_html_title(html, fallback=os.path.basename(urlparse(url).path.rstrip("/")) or url),
        )
        fetched_pages.append(page)
        if is_candidate(config, url):
            candidate_pages.append(page)
            if candidate_budget and len(candidate_pages) >= candidate_budget:
                _save_source_state(
                    config.source_name,
                    visited_urls=sorted(visited),
                    pending_queue=[{"url": pending_url, "depth": pending_depth} for pending_url, pending_depth in queue],
                    complete=False,
                    extra={"resume_supported": True},
                )
                break
        _sleep_crawl_delay(crawl_delay)
        if depth >= max_depth:
            _save_source_state(
                config.source_name,
                visited_urls=sorted(visited),
                pending_queue=[{"url": pending_url, "depth": pending_depth} for pending_url, pending_depth in queue],
                complete=False,
                extra={"resume_supported": True},
            )
            continue
        for link in _extract_html_links(html, url):
            if link in visited:
                continue
            if should_expand(config, link):
                queue.append((link, depth + 1))
        _save_source_state(
            config.source_name,
            visited_urls=sorted(visited),
            pending_queue=[{"url": pending_url, "depth": pending_depth} for pending_url, pending_depth in queue],
            complete=False,
            extra={"resume_supported": True},
        )

    _save_source_state(
        config.source_name,
        visited_urls=sorted(visited),
        pending_queue=[{"url": pending_url, "depth": pending_depth} for pending_url, pending_depth in queue],
        complete=not bool(queue),
        extra={"resume_supported": True},
    )
    return fetched_pages, candidate_pages


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_raw_dir(raw_root: str, source_name: str) -> str:
    path = os.path.join(raw_root, source_name)
    os.makedirs(path, exist_ok=True)
    return path


def _source_state_path(raw_root: str, source_name: str) -> str:
    return os.path.join(_source_raw_dir(raw_root, source_name), DISCOVERY_STATE_FILENAME)


def _load_source_state(source_name: str, raw_root: str = RAW_JSON_DIR) -> Dict[str, Any]:
    path = _source_state_path(raw_root, source_name)
    if not os.path.exists(path):
        return {"source": source_name, "visited_urls": [], "pending_queue": [], "complete": False}
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {"source": source_name, "visited_urls": [], "pending_queue": [], "complete": False}
    payload.setdefault("source", source_name)
    payload.setdefault("visited_urls", [])
    payload.setdefault("pending_queue", [])
    payload.setdefault("complete", False)
    return payload


def _save_source_state(
    source_name: str,
    *,
    visited_urls: Sequence[str],
    pending_queue: Sequence[Dict[str, Any]],
    complete: bool,
    raw_root: str = RAW_JSON_DIR,
    extra: Dict[str, Any] | None = None,
) -> str:
    payload = {
        "source": source_name,
        "visited_urls": list(visited_urls),
        "pending_queue": list(pending_queue),
        "complete": bool(complete),
        "updated_at": _utc_now(),
    }
    if extra:
        payload.update(extra)
    path = _source_state_path(raw_root, source_name)
    dump_json(path, payload)
    return path


def _source_raw_record_paths(source_name: str, raw_root: str = RAW_JSON_DIR) -> List[Path]:
    raw_dir = Path(_source_raw_dir(raw_root, source_name))
    paths = []
    for path in sorted(raw_dir.glob("*.json")):
        if path.name in IGNORED_SOURCE_RAW_FILENAMES:
            continue
        paths.append(path)
    return paths


def _source_triples_dir(triples_root: str, source_name: str) -> str:
    path = os.path.join(triples_root, source_name)
    os.makedirs(path, exist_ok=True)
    return path


def source_cleanup_targets(
    source_name: str,
    *,
    raw_root: str = RAW_JSON_DIR,
    triples_root: str = TRIPLES_DIR,
    evaluation_root: str = EVALUATION_DIR,
    chroma_root: str = CHROMA_DB_DIR,
) -> Dict[str, str]:
    return {
        "raw_dir": os.path.join(raw_root, source_name),
        "triples_dir": os.path.join(triples_root, source_name),
        "evaluation_report": os.path.join(evaluation_root, f"{source_name}_ingestion_report.json"),
        "chroma_dir": chroma_root if source_name == ACTIVE_SOURCE else os.path.join(chroma_root, source_name),
    }


def clear_source_ingestion_outputs(
    source_name: str,
    *,
    raw_root: str = RAW_JSON_DIR,
    triples_root: str = TRIPLES_DIR,
    evaluation_root: str = EVALUATION_DIR,
    chroma_root: str = CHROMA_DB_DIR,
) -> Dict[str, Any]:
    ensure_raw_source_directories(raw_root)
    targets = source_cleanup_targets(
        source_name,
        raw_root=raw_root,
        triples_root=triples_root,
        evaluation_root=evaluation_root,
        chroma_root=chroma_root,
    )
    deleted = {"directories": [], "files": []}
    missing = {"directories": [], "files": []}

    for key in ("raw_dir", "triples_dir"):
        path = targets[key]
        if os.path.isdir(path):
            shutil.rmtree(path)
            deleted["directories"].append(path)
        else:
            missing["directories"].append(path)

    report_path = targets["evaluation_report"]
    if os.path.isfile(report_path):
        os.remove(report_path)
        deleted["files"].append(report_path)
    else:
        missing["files"].append(report_path)

    ensure_raw_source_directories(raw_root)
    return {
        "source": source_name,
        "runtime_managed": {
            "chroma_dir": targets["chroma_dir"],
        },
        "deleted": deleted,
        "missing": missing,
        "generated_at": _utc_now(),
    }


def _load_json_if_exists(path: str) -> Any:
    if not os.path.exists(path):
        return None
    return load_json(path)


def _load_first_existing_json(*paths: str) -> Any:
    for path in paths:
        if path and os.path.exists(path):
            return load_json(path)
    return None


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


def _cache_live_raw_payload(source_name: str, raw_id: str, payload: Dict[str, Any], raw_root: str = RAW_JSON_DIR) -> str:
    cache_payload = dict(payload or {})
    cache_payload.setdefault("cached_at", _utc_now())
    return _write_source_raw_payload(raw_root, source_name, raw_id, cache_payload)


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
                str(payload.get("origin") or record.get("origin") or "api"),
                "triple_candidate",
                source_name=source_name,
                source_role=payload.get("source_role") or record.get("source_role") or SOURCE_ROLE,
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
                str(payload.get("origin") or record.get("origin") or "api"),
                "embedding_chunk",
                source_name=source_name,
                source_role=payload.get("source_role") or record.get("source_role") or SOURCE_ROLE,
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
    extra_report_fields: Dict[str, Any] | None = None,
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
    report.update(dict(extra_report_fields or {}))
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
            max_depth=2,
        )
    if source_name == "nasa":
        return ControlledSourceConfig(
            source_name=source_name,
            allowed_domains=("science.nasa.gov", "nssdc.gsfc.nasa.gov", "solarsystem.nasa.gov"),
            seed_items=NASA_SEEDS,
            timeout=10,
            crawl_delay=1.2,
            max_depth=2,
        )
    if source_name == "esa":
        return ControlledSourceConfig(
            source_name=source_name,
            allowed_domains=("www.esa.int", "esa.int"),
            seed_items=ESA_MISSION_SEEDS,
            timeout=10,
            crawl_delay=1.2,
            max_depth=2,
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
    payload = _load_first_existing_json(
        os.path.join(RAW_JSON_DIR, "zh_wikipedia", f"{safe_title(title)}.json"),
        os.path.join(RAW_JSON_DIR, "zh_wikipedia", f"{safe}.json"),
        os.path.join(RAW_JSON_DIR, f"{safe}_html.json"),
    )
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


def _legacy_zh_record(title: str, payload: Dict[str, Any] | None, warning_reason: str, warnings: List[str]) -> Dict[str, Any] | None:
    safe = safe_title(title)
    triples = _triples_items_from_payload(_load_json_if_exists(os.path.join(TRIPLES_DIR, f"{safe}_triples.json")))
    narratives = _narratives_items_from_payload(_load_json_if_exists(os.path.join(TRIPLES_DIR, f"{safe}_narratives.json")))
    if not triples and not narratives:
        return None
    warnings.append(f"zh_wikipedia legacy triples fallback for {title}: {warning_reason}")
    source_url = str((payload or {}).get("url") or f"https://zh.wikipedia.org/wiki/{title}")
    return {
        "raw_id": title,
        "raw_payload": dict(payload or {"title": title, "url": source_url}),
        "title": title,
        "triples": triples,
        "narratives": narratives,
        "source_url": source_url,
        "source_role": SOURCE_ROLE,
        "origin": str((payload or {}).get("origin") or "html_fallback"),
    }


def _build_zh_record_from_raw_payload(payload: Dict[str, Any]) -> tuple[Dict[str, Any] | None, str]:
    normalized_payload = dict(payload or {})
    title = str(normalized_payload.get("title") or "").strip()
    if not title:
        return None, "missing_title"
    html = str(normalized_payload.get("html") or "").strip()
    if not html:
        return None, "missing_html"

    normalized_payload.setdefault("category", "Auto")
    normalized_payload["source"] = "zh_wikipedia"
    normalized_payload["source_name"] = "zh_wikipedia"
    normalized_payload["source_role"] = SOURCE_ROLE
    normalized_payload["schema_version"] = get_source_schema_version("zh_wikipedia")
    normalized_payload["origin"] = str(normalized_payload.get("origin") or "html_fallback")

    preprocessor = WikiPreprocessor(
        source_name="zh_wikipedia",
        source_role=SOURCE_ROLE,
        schema_version=get_source_schema_version("zh_wikipedia"),
    )
    result, error = preprocessor.process_json_data(normalized_payload)
    if error or not result:
        return None, str(error or "preprocess_failed")

    narratives = WikiPreprocessor.chunks_to_narratives(
        result.get("embedding_chunks", []),
        title,
        source_name="zh_wikipedia",
        source_role=SOURCE_ROLE,
        schema_version=get_source_schema_version("zh_wikipedia"),
    )
    return (
        {
            "raw_id": title,
            "raw_payload": normalized_payload,
            "title": title,
            "triples": list(result.get("all_triples", [])),
            "narratives": narratives,
            "source_url": str(normalized_payload.get("url") or ""),
            "source_role": SOURCE_ROLE,
            "origin": str(normalized_payload.get("origin") or "html_fallback"),
        },
        "",
    )


def _build_zh_records(limit: int, mode: str) -> tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    config = source_config_for("zh_wikipedia")
    warnings: List[str] = []
    errors: List[str] = []
    skipped_urls: List[str] = []
    records: List[Dict[str, Any]] = []

    for seed in limit_seed_items(config.seed_items, limit):
        payload = _zh_seed_payload(seed, mode=mode, warnings=warnings)
        title = str((payload or {}).get("title") or seed.get("title") or "").strip()
        source_url = str((payload or {}).get("url") or f"https://zh.wikipedia.org/wiki/{title}")
        if not is_allowed_source_url(config, source_url):
            skipped_urls.append(source_url)
            continue
        record = None
        fallback_reason = ""
        if payload:
            record, fallback_reason = _build_zh_record_from_raw_payload(payload)
        else:
            fallback_reason = "raw_html_missing"

        if record is None:
            record = _legacy_zh_record(title, payload, fallback_reason, warnings)
        if record is None:
            if fallback_reason:
                warnings.append(f"zh_wikipedia skipped for {title}: {fallback_reason}")
            continue
        records.append(record)
    return records, warnings, errors, skipped_urls


def _wikidata_label(entity: Dict[str, Any], qid: str) -> str:
    labels = entity.get("labels", {})
    return str(
        labels.get("zh-hans", {}).get("value")
        or labels.get("zh", {}).get("value")
        or labels.get("en", {}).get("value")
        or qid
    ).strip()


def _wikidata_neighbors_from_entities(raw_payload: Dict[str, Any]) -> List[Dict[str, str]]:
    neighbors: List[Dict[str, str]] = []
    entities = raw_payload.get("entities", {})
    for entity in entities.values():
        claims = entity.get("claims", {})
        for property_id in PROPERTY_RELATION_MAP:
            for claim in claims.get(property_id, []):
                mainsnak = claim.get("mainsnak", {})
                datavalue = mainsnak.get("datavalue", {})
                raw_value = datavalue.get("value")
                if isinstance(raw_value, dict) and str(raw_value.get("id") or "").upper().startswith("Q"):
                    neighbors.append({"qid": str(raw_value.get("id") or "").upper(), "title": ""})
    return neighbors


def _wikidata_fixture_neighbors(record: Dict[str, Any], fixture_by_title: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    neighbors: List[Dict[str, str]] = []
    for triple in record.get("triples", []):
        candidate = str(triple.get("object") or "").strip()
        if candidate and candidate in fixture_by_title:
            neighbor_record = fixture_by_title[candidate]
            neighbors.append({"qid": str(neighbor_record.get("qid") or "").strip(), "title": candidate})
    return neighbors


def _wikidata_fixture_entity_maps(fixture_payload: Dict[str, Any]) -> tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
    qid_to_title: Dict[str, str] = {}
    relation_map_by_qid: Dict[str, Dict[str, str]] = {}
    for item in fixture_payload.get("records", []):
        title = str(item.get("title") or "").strip()
        qid = str(item.get("qid") or "").strip().upper()
        if qid and title:
            qid_to_title[qid] = title
        if not qid:
            continue
        relation_map = relation_map_by_qid.setdefault(qid, {})
        for triple in item.get("triples", []):
            relation = str(triple.get("relation") or "").strip()
            obj = str(triple.get("object") or "").strip()
            if relation and obj:
                relation_map.setdefault(relation, obj)
    return qid_to_title, relation_map_by_qid


def _rewrite_wikidata_record_with_fixture(
    record: Dict[str, Any],
    *,
    qid: str,
    fixture_relation_map: Dict[str, Dict[str, str]],
    qid_to_title: Dict[str, str],
) -> Dict[str, Any]:
    relation_overrides = fixture_relation_map.get(str(qid or "").strip().upper(), {})
    rewritten = dict(record or {})
    normalized_title = qid_to_title.get(str(qid or "").strip().upper(), str(rewritten.get("title") or "").strip())
    if normalized_title:
        rewritten["title"] = normalized_title

    rewritten_triples: List[Dict[str, Any]] = []
    for triple in rewritten.get("triples", []):
        payload = dict(triple)
        relation = str(payload.get("relation") or "").strip()
        obj = str(payload.get("object") or "").strip()
        if obj.upper().startswith("Q"):
            payload["object"] = qid_to_title.get(obj.upper(), obj)
        if relation in relation_overrides:
            payload["object"] = relation_overrides[relation]
        rewritten_triples.append(payload)
    rewritten["triples"] = rewritten_triples
    return rewritten


def _load_wikidata_raw_payload(qid: str) -> Dict[str, Any] | None:
    if not qid:
        return None
    path = os.path.join(RAW_JSON_DIR, "wikidata", f"{qid}.json")
    return _load_json_if_exists(path)


def _nasa_candidate_score(url: str) -> int:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if _path_looks_binary(path):
        return -1
    if any(token in path for token in NASA_SKIP_PATH_KEYWORDS):
        return -1
    score = 0
    if "factsheet" in path:
        score += 6
    if "/solar-system/" in path or "/planetary/" in path:
        score += 3
    if "/planets/" in path or "/moons/" in path or "dwarf-planet" in path:
        score += 2
    if any(token in path for token in NASA_DISCOVERY_KEYWORDS):
        score += 2
    if path.rstrip("/").endswith(("overview", "overview/index.html")):
        score += 1
    return score


def _should_expand_nasa_url(config: ControlledSourceConfig, url: str) -> bool:
    if not is_allowed_source_url(config, url):
        return False
    parsed = urlparse(url)
    path = parsed.path.lower()
    if _path_looks_binary(path) or any(token in path for token in NASA_SKIP_PATH_KEYWORDS):
        return False
    return _is_high_value_nasa_url(url)


def _looks_like_nasa_candidate(config: ControlledSourceConfig, url: str) -> bool:
    return is_allowed_source_url(config, url) and _is_high_value_nasa_url(url) and _nasa_candidate_score(url) > 0


def _infer_title_from_url(url: str, hints: Dict[str, str], fallback: str = "") -> str:
    lowered = str(url or "").lower()
    for token, title in hints.items():
        if token in lowered:
            return title
    return fallback


def _path_segments(url: str) -> List[str]:
    return [segment for segment in urlparse(url).path.lower().split("/") if segment]


def _title_contains_any(title: str, keywords: Sequence[str]) -> bool:
    lowered = str(title or "").lower()
    return any(keyword in lowered for keyword in keywords)


def _is_high_value_nasa_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    segments = _path_segments(url)
    if any(keyword in path for keyword in NASA_SKIP_PATH_KEYWORDS):
        return False
    if path.rstrip("/") in {"/planetary/factsheet", "/solar-system", "/solar-system/planets", "/moons/overview"}:
        return False
    if "factsheet" in path:
        return True
    if any(keyword in path for keyword in ("10-things", "movie-night", "multimedia", "resources", "planetary-analogs")):
        return False
    if len(segments) < 3:
        return False
    if segments[-1] in NASA_GENERIC_LANDING_SEGMENTS:
        return False
    if segments[-2] in NASA_GENERIC_LANDING_SEGMENTS and segments[-1] in {"overview", "in-depth", "facts"}:
        return False
    return any(segment in path for segment in NASA_HIGH_VALUE_PATH_SEGMENTS) and (
        any(token in path for token in NASA_TITLE_HINTS)
        or any(segment in {"asteroids", "comets", "moons", "dwarf-planets"} for segment in segments)
    )


def _is_high_value_nasa_payload(payload: Dict[str, Any]) -> bool:
    url = str(payload.get("source_url") or payload.get("url") or "").strip()
    title = str(payload.get("title") or "").strip()
    html = str(payload.get("html") or "")
    if not url or not _is_high_value_nasa_url(url):
        return False
    if _title_contains_any(title, NASA_NOISE_TITLE_KEYWORDS):
        return False
    return has_strict_fact_sheet_fields(html) or bool(_infer_title_from_url(url, NASA_TITLE_HINTS, "")) or any(
        needle in html.lower() for needle in ("mass", "radius", "atmosphere", "orbit", "planet", "moon", "comet", "asteroid")
    )


def _is_primary_esa_host(url: str) -> bool:
    return _hostname(url) in ESA_PRIMARY_HOSTS


def _is_high_value_esa_payload(payload: Dict[str, Any]) -> bool:
    url = str(payload.get("source_url") or payload.get("url") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not url or not _is_primary_esa_host(url):
        return False
    if _title_contains_any(title, ESA_NOISE_TITLE_KEYWORDS):
        return False
    lowered_title = title.lower()
    lowered_path = urlparse(url).path.lower()
    return any(keyword in lowered_title for keyword in ESA_HIGH_VALUE_TITLE_KEYWORDS) or any(
        keyword in lowered_path for keyword in ("juice", "rosetta", "gaia", "solar_orbiter", "solar-orbiter", "mars_express", "mars-express", "bepicolombo", "smart-1", "facts_about")
    )


def _nasa_record_from_payload(adapter: NasaPipelineAdapter, payload: Dict[str, Any]) -> Dict[str, Any]:
    html = str(payload.get("html") or "")
    title = str(payload.get("title") or "").strip() or _infer_title_from_url(str(payload.get("source_url") or payload.get("url") or ""), NASA_TITLE_HINTS, "NASA 页面")
    source_url = str(payload.get("source_url") or payload.get("url") or "").strip()
    fetched_at = str(payload.get("fetched_at") or _utc_now())
    if has_strict_fact_sheet_fields(html):
        payload = dict(payload)
        payload["title"] = title
        return adapter._record_from_fact_sheet(payload)
    text = html_to_text(html)
    return adapter._record_from_offline_raw(
        {
            "title": title,
            "url": source_url,
            "html": html,
            "text": text,
            "raw_text": text,
            "crawl_time": fetched_at,
        },
        fetched_at,
    )


def _discover_nasa_candidate_pages(config: ControlledSourceConfig, timeout: int, crawl_delay: float, warnings: List[str], limit: int) -> tuple[List[DiscoveredHtmlPage], List[DiscoveredHtmlPage]]:
    seed_urls = list(NASA_DISCOVERY_SEED_URLS) + [
        str(item.get("url") or "").strip()
        for item in NASA_FACT_SHEETS.values()
        if str(item.get("url") or "").strip()
    ]
    return _discover_html_pages_bfs(
        config=config,
        seed_urls=seed_urls,
        timeout=timeout,
        crawl_delay=crawl_delay,
        max_depth=config.max_depth,
        max_fetch_pages=max(limit * 6, 60),
        warnings=warnings,
        should_expand=_should_expand_nasa_url,
        is_candidate=_looks_like_nasa_candidate,
    )


def _esa_candidate_score(url: str) -> int:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if _path_looks_binary(path):
        return -1
    if any(token.lower() in path for token in ESA_SKIP_PATH_KEYWORDS):
        return -1
    score = 0
    if "science_exploration/space_science" in path.lower():
        score += 3
    for token in ESA_TARGET_HINTS:
        if token in path:
            score += 3
    if "/mission" in path or path.rstrip("/").endswith(("juice", "rosetta", "gaia", "solar_orbiter", "mars_express", "venus_express", "smart-1", "bepicolombo")):
        score += 2
    return score


def _should_expand_esa_url(config: ControlledSourceConfig, url: str) -> bool:
    if not is_allowed_source_url(config, url):
        return False
    if not _is_primary_esa_host(url):
        return False
    parsed = urlparse(url)
    path = parsed.path.lower()
    if _path_looks_binary(path) or any(token.lower() in path for token in ESA_SKIP_PATH_KEYWORDS):
        return False
    return any(
        token in path
        for token in (
            "/science_exploration/",
            "/space_science/",
            "juice",
            "rosetta",
            "gaia",
            "solar_orbiter",
            "solar-orbiter",
            "mars_express",
            "mars-express",
            "venus_express",
            "venus-express",
            "smart-1",
            "bepicolombo",
            "facts_about",
            "facts-about",
        )
    )


def _looks_like_esa_candidate(config: ControlledSourceConfig, url: str) -> bool:
    return is_allowed_source_url(config, url) and _is_primary_esa_host(url) and _esa_candidate_score(url) > 0


def _infer_esa_targets(title: str, url: str, text: str) -> List[str]:
    haystack = " ".join([str(title or "").lower(), str(url or "").lower(), str(text or "").lower()])
    targets: List[str] = []
    for token, values in ESA_TARGET_HINTS.items():
        if token in haystack:
            for value in values:
                if value not in targets:
                    targets.append(value)
    return targets


def _discover_esa_candidate_pages(config: ControlledSourceConfig, timeout: int, crawl_delay: float, warnings: List[str], limit: int) -> tuple[List[DiscoveredHtmlPage], List[DiscoveredHtmlPage]]:
    seed_urls = list(ESA_DISCOVERY_SEED_URLS) + [
        str(seed.get("url") or "").strip()
        for seed in ESA_MISSION_SEEDS
        if str(seed.get("url") or "").strip()
    ]
    return _discover_html_pages_bfs(
        config=config,
        seed_urls=seed_urls,
        timeout=timeout,
        crawl_delay=crawl_delay,
        max_depth=config.max_depth,
        max_fetch_pages=max(limit * 6, 40),
        warnings=warnings,
        should_expand=_should_expand_esa_url,
        is_candidate=_looks_like_esa_candidate,
    )


def _build_esa_live_record_from_url(url: str, timeout: int, *, prefetched_html: str = "", discovery_depth: int | None = None) -> Dict[str, Any]:
    html = prefetched_html or _fetch_html(url, timeout)
    title = _extract_html_title(html, fallback=os.path.basename(urlparse(url).path.rstrip("/")) or "ESA 任务")
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    targets = _infer_esa_targets(title, url, text)
    triples = [{"relation": "OPERATED_BY", "object": "ESA", "source_url": url, "source_field": "live_page"}]
    for target in targets:
        triples.append({"relation": "HAS_MISSION_TARGET", "object": target, "source_url": url, "source_field": "live_page"})
    return {
        "raw_id": title,
        "raw_payload": {"title": title, "url": url, "html": html, "fetched_at": _utc_now(), "discovery_depth": discovery_depth},
        "title": title,
        "triples": triples,
        "narratives": [{
            "section": "任务",
            "content": text[:800],
            "keywords": [title, "ESA", "太阳系任务"] + targets[:4],
        }],
        "source_url": url,
    }


def _build_wikidata_records(limit: int, mode: str) -> tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    config = source_config_for("wikidata")
    warnings: List[str] = []
    errors: List[str] = []
    skipped_urls: List[str] = []
    records: List[Dict[str, Any]] = []
    pending_missing_records: List[str] = []
    seeds = limit_seed_items(config.seed_items, max(limit, len(config.seed_items)))
    fixture_path = os.path.join(SOURCE_FIXTURES_DIR, "wikidata", "solar_system_fixture.json")
    raw_fixture_path = os.path.join(RAW_JSON_DIR, "wikidata", "solar_system_fixture.json")
    fixture_payload = _load_first_existing_json(fixture_path, raw_fixture_path) or {"records": []}
    fixture_by_title = {
        str(item.get("title") or "").strip(): item
        for item in fixture_payload.get("records", [])
        if str(item.get("title") or "").strip()
    }
    fixture_by_qid = {
        str(item.get("qid") or "").strip().upper(): item
        for item in fixture_payload.get("records", [])
        if str(item.get("qid") or "").strip()
    }
    qid_to_title, fixture_relation_map = _wikidata_fixture_entity_maps(fixture_payload)

    queue = deque(
        {
            "title": str(seed.get("entity") or "").strip(),
            "qid": str(seed.get("qid") or "").strip().upper(),
            "depth": 0,
        }
        for seed in seeds
    )
    seen_qids = set()
    seen_titles = set()

    while queue and len(records) < limit:
        item = queue.popleft()
        title = str(item.get("title") or "").strip()
        qid = str(item.get("qid") or "").strip().upper()
        depth = int(item.get("depth", 0) or 0)
        identity = qid or title
        if not identity or identity in seen_qids or identity in seen_titles:
            continue
        if qid:
            seen_qids.add(qid)
        if title:
            seen_titles.add(title)

        source_url = WIKIDATA_ENTITY_URL.format(qid=qid) if qid else ""
        if source_url and not is_allowed_source_url(config, source_url):
            skipped_urls.append(source_url)
            continue

        record = None
        raw_payload = None
        neighbors: List[Dict[str, str]] = []
        adapter = WikidataFixtureAdapter(entity=qid or title, timeout=config.timeout)

        if mode == "auto":
            record = fixture_by_qid.get(qid) or fixture_by_title.get(title)
            raw_payload = {"record": record, "fixture_source": os.path.basename(fixture_path)} if record else None
            if record:
                neighbors = _wikidata_fixture_neighbors(record, fixture_by_title)

        cached_raw = _load_wikidata_raw_payload(qid) if qid and record is None else None
        if cached_raw:
            raw_payload = cached_raw
            normalized = adapter.normalize_records(raw_payload)
            if normalized:
                record = normalized[0]
                entity_payload = next(iter((raw_payload.get("entities") or {}).values()), {})
                if entity_payload:
                    title = _wikidata_label(entity_payload, qid)
                record = _rewrite_wikidata_record_with_fixture(
                    record,
                    qid=qid,
                    fixture_relation_map=fixture_relation_map,
                    qid_to_title=qid_to_title,
                )
                neighbors = _wikidata_neighbors_from_entities(raw_payload)

        if record is None and mode in {"live", "auto"}:
            try:
                raw_payload = adapter.fetch_live()
                if raw_payload:
                    _cache_live_raw_payload("wikidata", qid or title or "wikidata_live", raw_payload)
                normalized = adapter.normalize_records(raw_payload)
                record = normalized[0] if normalized else None
                if record is not None:
                    record = _rewrite_wikidata_record_with_fixture(
                        record,
                        qid=qid,
                        fixture_relation_map=fixture_relation_map,
                        qid_to_title=qid_to_title,
                    )
                neighbors = _wikidata_neighbors_from_entities(raw_payload)
            except Exception as exc:
                warnings.append(f"wikidata live fallback for {title or qid}: {exc}")

        if record is None:
            record = fixture_by_qid.get(qid) or fixture_by_title.get(title)
            raw_payload = {"record": record, "fixture_source": os.path.basename(fixture_path)} if record else None
            if record:
                neighbors = _wikidata_fixture_neighbors(record, fixture_by_title)

        if not record:
            if mode == "auto":
                pending_missing_records.append(title or qid)
                warnings.append(f"wikidata pending missing record for {title or qid}")
            else:
                errors.append(f"wikidata record missing for {title or qid}")
            continue

        normalized_title = str(record.get("title") or title or qid).strip()
        records.append(
            {
                "raw_id": qid or normalized_title,
                "raw_payload": dict(raw_payload or {"record": record}),
                "title": normalized_title,
                "triples": list(record.get("triples", [])),
                "narratives": list(record.get("narratives", [])),
                "source_url": source_url or _record_source_url(record),
            }
        )

        if depth >= config.max_depth:
            continue

        for neighbor in neighbors:
            neighbor_qid = str(neighbor.get("qid") or "").strip().upper()
            neighbor_title = str(neighbor.get("title") or "").strip()
            if (
                mode not in {"live", "auto"}
                and neighbor_qid
                and neighbor_qid not in fixture_by_qid
                and _load_wikidata_raw_payload(neighbor_qid) is None
            ):
                continue
            if not neighbor_title and neighbor_qid in fixture_by_qid:
                neighbor_title = str(fixture_by_qid[neighbor_qid].get("title") or "").strip()
            if (neighbor_qid and neighbor_qid not in seen_qids) or (neighbor_title and neighbor_title not in seen_titles):
                queue.append({"title": neighbor_title, "qid": neighbor_qid, "depth": depth + 1})

    _set_collection_context("wikidata", pending_missing_records=pending_missing_records)
    return records[:limit], warnings, errors, skipped_urls


def _build_nasa_records(limit: int, mode: str) -> tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    config = source_config_for("nasa")
    warnings: List[str] = []
    errors: List[str] = []
    skipped_urls: List[str] = []
    records: List[Dict[str, Any]] = []
    adapter = NasaPipelineAdapter(timeout=config.timeout)
    seen_titles = set()
    seen_urls = set()
    fixture_path = os.path.join(SOURCE_FIXTURES_DIR, "nasa", "discovery_fixture.json")
    raw_fixture_path = os.path.join(RAW_JSON_DIR, "nasa", "discovery_fixture.json")
    fixture_payload = _load_first_existing_json(fixture_path, raw_fixture_path) or {"records": []}
    low_coverage_warning = ""

    for raw_path in _source_raw_record_paths("nasa"):
        if len(records) >= limit:
            break
        payload = load_json(str(raw_path))
        source_url = str(payload.get("url") or payload.get("source_url") or NASA_FACT_SHEETS.get(str(payload.get("title") or ""), {}).get("url") or "")
        if source_url and not is_allowed_source_url(config, source_url):
            skipped_urls.append(source_url)
            continue
        if not _is_high_value_nasa_payload(payload):
            if source_url:
                skipped_urls.append(source_url)
            continue
        title = str(payload.get("title") or raw_path.stem).strip()
        if title in seen_titles or source_url in seen_urls:
            continue
        record = _nasa_record_from_payload(
            adapter,
            {
                "title": title,
                "source_url": source_url,
                "url": source_url,
                "html": str(payload.get("html") or ""),
                "fetched_at": str(payload.get("fetched_at") or payload.get("crawl_time") or _utc_now()),
            },
        )
        seen_titles.add(title)
        if source_url:
            seen_urls.add(source_url)
        records.append(
            {
                "raw_id": raw_path.stem,
                "raw_payload": payload,
                "title": str(record.get("title") or title),
                "triples": list(record.get("triples", [])),
                "narratives": list(record.get("narratives", [])),
                "source_url": source_url,
            }
        )

    if mode in {"live", "auto"} and len(records) < limit:
        _fetched_pages, candidate_pages = _discover_nasa_candidate_pages(config, config.timeout, config.crawl_delay, warnings, limit)
        ordered_candidate_pages = sorted(candidate_pages, key=lambda page: (-_nasa_candidate_score(page.url), page.depth, page.url))
        for page in ordered_candidate_pages:
            if len(records) >= limit:
                break
            url = page.url
            if url in seen_urls:
                continue
            html = page.html
            title = _infer_title_from_url(url, NASA_TITLE_HINTS, page.title or "NASA 页面")
            raw_payload = {
                "title": title,
                "source_record_id": safe_title(title or url),
                "source_url": url,
                "url": url,
                "html": html,
                "fetched_at": _utc_now(),
                "discovery_depth": page.depth,
            }
            if not _is_high_value_nasa_payload(raw_payload):
                skipped_urls.append(url)
                seen_urls.add(url)
                continue
            _cache_live_raw_payload("nasa", str(raw_payload.get("source_record_id") or title or url), raw_payload)
            record = _nasa_record_from_payload(adapter, raw_payload)
            normalized_title = str(record.get("title") or title or url).strip()
            if normalized_title in seen_titles:
                seen_urls.add(url)
                continue
            seen_titles.add(normalized_title)
            seen_urls.add(url)
            records.append(
                {
                    "raw_id": str(raw_payload.get("source_record_id") or normalized_title),
                    "raw_payload": raw_payload,
                    "title": normalized_title,
                    "triples": list(record.get("triples", [])),
                    "narratives": list(record.get("narratives", [])),
                    "source_url": url,
                }
            )

    for item in fixture_payload.get("records", []):
        if len(records) >= limit:
            break
        title = str(item.get("title") or "").strip()
        source_url = str(item.get("source_url") or item.get("url") or "").strip()
        if not title or title in seen_titles or source_url in seen_urls:
            continue
        if source_url and not is_allowed_source_url(config, source_url):
            skipped_urls.append(source_url)
            continue
        if not _is_high_value_nasa_payload(item):
            if source_url:
                skipped_urls.append(source_url)
            continue
        record = _nasa_record_from_payload(
            adapter,
            {
                "title": title,
                "source_url": source_url,
                "url": source_url,
                "html": str(item.get("html") or ""),
                "fetched_at": str(item.get("fetched_at") or _utc_now()),
            },
        )
        seen_titles.add(title)
        if source_url:
            seen_urls.add(source_url)
        records.append(
            {
                "raw_id": safe_title(title),
                "raw_payload": dict(item),
                "title": str(record.get("title") or title),
                "triples": list(record.get("triples", [])),
                "narratives": list(record.get("narratives", [])),
                "source_url": source_url,
            }
        )

    if not records:
        if mode in {"auto", "offline"}:
            fallback_payload = {
                "title": "火星",
                "source_record_id": "nasa-fallback-mars-fact-sheet",
                "source_url": NASA_FACT_SHEETS["火星"]["url"],
                "html": NASA_MARS_STRICT_TABLE_FALLBACK_HTML,
                "fetched_at": _utc_now(),
            }
            fallback_record = adapter._record_from_fact_sheet(fallback_payload)
            records.append(
                {
                    "raw_id": "nasa-fallback-mars-fact-sheet",
                    "raw_payload": fallback_payload,
                    "title": str(fallback_record.get("title") or "火星"),
                    "triples": list(fallback_record.get("triples", [])),
                    "narratives": list(fallback_record.get("narratives", [])),
                    "source_url": fallback_payload["source_url"],
                }
            )
            warnings.append("nasa raw records unavailable; used bundled Mars fact-sheet fallback for debugging")
        else:
            errors.append("nasa raw records unavailable")
    elif limit > len(records):
        low_coverage_warning = (
            f"nasa low coverage: retained {len(records)} high-value fact pages under the current allowlist/candidate filter "
            f"(requested limit={limit})"
        )
        warnings.append(low_coverage_warning)
    _set_collection_context("nasa", low_coverage_warning=low_coverage_warning)
    return records[:limit], warnings, errors, skipped_urls


def _build_esa_records(limit: int, mode: str) -> tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    config = source_config_for("esa")
    warnings: List[str] = []
    errors: List[str] = []
    skipped_urls: List[str] = []
    records: List[Dict[str, Any]] = []
    fixture_path = os.path.join(SOURCE_FIXTURES_DIR, "esa", "smoke_fixture.json")
    raw_fixture_path = os.path.join(RAW_JSON_DIR, "esa", "smoke_fixture.json")
    fixture_payload = _load_first_existing_json(fixture_path, raw_fixture_path) or {"records": []}
    fixture_by_title = {
        str(item.get("title") or "").strip(): item
        for item in fixture_payload.get("records", [])
        if str(item.get("title") or "").strip()
    }
    seen_titles = set()
    seen_urls = set()

    for raw_path in _source_raw_record_paths("esa"):
        if len(records) >= limit:
            break
        payload = load_json(str(raw_path))
        source_url = str(payload.get("url") or payload.get("source_url") or "").strip()
        if source_url and not is_allowed_source_url(config, source_url):
            skipped_urls.append(source_url)
            continue
        if not _is_high_value_esa_payload(payload):
            if source_url:
                skipped_urls.append(source_url)
            continue
        title = str(payload.get("title") or raw_path.stem).strip()
        if not title or title in seen_titles or source_url in seen_urls:
            continue
        record = _build_esa_live_record_from_url(
            source_url or title,
            config.timeout,
            prefetched_html=str(payload.get("html") or ""),
            discovery_depth=payload.get("discovery_depth"),
        )
        seen_titles.add(title)
        if source_url:
            seen_urls.add(source_url)
        records.append(
            {
                "raw_id": raw_path.stem,
                "raw_payload": payload,
                "title": str(record.get("title") or title),
                "triples": list(record.get("triples", [])),
                "narratives": list(record.get("narratives", [])),
                "source_url": source_url,
            }
        )

    if mode in {"live", "auto"} and len(records) < limit:
        _fetched_pages, candidate_pages = _discover_esa_candidate_pages(config, config.timeout, config.crawl_delay, warnings, limit)
        ordered_candidate_pages = sorted(candidate_pages, key=lambda page: (-_esa_candidate_score(page.url), page.depth, page.url))
        for page in ordered_candidate_pages:
            if len(records) >= limit:
                break
            url = page.url
            if url in seen_urls:
                continue
            candidate_payload = {
                "title": page.title or _extract_html_title(page.html, fallback=os.path.basename(urlparse(url).path.rstrip("/")) or url),
                "source_url": url,
                "url": url,
                "html": page.html,
            }
            if not _is_high_value_esa_payload(candidate_payload):
                skipped_urls.append(url)
                seen_urls.add(url)
                continue
            try:
                record = _build_esa_live_record_from_url(url, config.timeout, prefetched_html=page.html, discovery_depth=page.depth)
            except Exception as exc:
                warnings.append(f"esa live fallback for {url}: {exc}")
                continue
            _cache_live_raw_payload("esa", str(record.get("raw_id") or page.title or url), dict(record.get("raw_payload", {})))
            title = str(record.get("title") or "").strip()
            if not title or title in seen_titles:
                seen_urls.add(url)
                continue
            seen_titles.add(title)
            seen_urls.add(url)
            records.append(record)

    for seed in config.seed_items:
        if len(records) >= limit:
            break
        title = str(seed.get("title") or "").strip()
        url = str(seed.get("url") or "").strip()
        if title in seen_titles or url in seen_urls:
            continue
        if url and not is_allowed_source_url(config, url):
            skipped_urls.append(url)
            continue
        fixture_record = fixture_by_title.get(title)
        if fixture_record:
            records.append(
                {
                    "raw_id": title,
                    "raw_payload": {"record": fixture_record, "fixture_source": os.path.basename(fixture_path)},
                    "title": title,
                    "triples": list(fixture_record.get("triples", [])),
                    "narratives": list(fixture_record.get("narratives", [])),
                    "source_url": url,
                }
            )
            seen_titles.add(title)
            if url:
                seen_urls.add(url)

    for title, fixture_record in fixture_by_title.items():
        if len(records) >= limit:
            break
        if title in seen_titles:
            continue
        source_url = str(next((triple.get("source_url") for triple in fixture_record.get("triples", []) if triple.get("source_url")), "") or "")
        if source_url and not is_allowed_source_url(config, source_url):
            skipped_urls.append(source_url)
            continue
        records.append(
            {
                "raw_id": title,
                "raw_payload": {"record": fixture_record, "fixture_source": os.path.basename(fixture_path)},
                "title": title,
                "triples": list(fixture_record.get("triples", [])),
                "narratives": list(fixture_record.get("narratives", [])),
                "source_url": source_url,
            }
        )
        seen_titles.add(title)
        if source_url:
            seen_urls.add(source_url)

    return records[:limit], warnings, errors, skipped_urls


def collect_records_for_source(source_name: str, limit: int, mode: str = "auto") -> tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    if source_name == "zh_wikipedia":
        return _build_zh_records(limit, "offline" if mode == "auto" else mode)
    if source_name == "wikidata":
        return _build_wikidata_records(limit, mode)
    if source_name == "nasa":
        return _build_nasa_records(limit, mode)
    if source_name == "esa":
        return _build_esa_records(limit, mode)
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
    _consume_collection_context(source_name)

    records, warnings, errors, skipped_urls = collect_records_for_source(source_name, limit, mode=mode)
    triples_dir = _source_triples_dir(TRIPLES_DIR, source_name)
    collection_context = _consume_collection_context(source_name)
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
        extra_report_fields=collection_context,
    )
    graph_written, chroma_written, details, extra_warnings, extra_errors = _materialize_shadow_namespace(source_name, triples_dir)
    report["graph_written"] = graph_written
    report["chroma_written"] = chroma_written
    report["materialization_details"] = details
    report["warnings"] = list(report.get("warnings", [])) + list(extra_warnings)
    report["errors"] = list(report.get("errors", [])) + list(extra_errors)
    report["generated_at"] = _utc_now()
    dump_json(os.path.join(EVALUATION_DIR, f"{source_name}_ingestion_report.json"), report)
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Controlled solar-system source ingestion entrypoint.")
    parser.add_argument("--source", required=True, choices=tuple(RAW_SOURCES) + ("all",))
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--mode", choices=("auto", "offline", "live"), default="auto")
    args = parser.parse_args()

    sources = list(RAW_SOURCES) if args.source == "all" else [args.source]
    reports = [run_controlled_ingestion(source_name, limit=args.limit, mode=args.mode) for source_name in sources]
    print(json.dumps({"sources": sources, "reports": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

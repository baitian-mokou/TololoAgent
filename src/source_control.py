"""
Source control helpers.

本模块负责统一 metadata、source registry 视图和 source-aware 命名空间。
当前默认 active source 仍为中文维基百科；非 active source 通过独立
namespace 预留扩源能力。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from config import ACTIVE_SOURCE, FORMALLY_INTEGRATED_SOURCES, SOURCE_REGISTRY


SOURCE_ROLE = "primary"
SOURCE_SCHEMA_VERSION = f"{ACTIVE_SOURCE}_single_source_v1"
DEFAULT_SOURCE_FILTER = (ACTIVE_SOURCE,)
SOURCE_STATUS_ACTIVE = "active"
SOURCE_STATUS_DISABLED = "disabled"
FORMAL_SOURCE_STATUS_FORMALLY_INTEGRATED = "formally_integrated_shadow"

ORIGIN_API = "api"
ORIGIN_HTML_FALLBACK = "html_fallback"
ORIGIN_INTERNAL_LINK = "internal_link"

RECORD_TYPE_TRIPLE_CANDIDATE = "triple_candidate"
RECORD_TYPE_EMBEDDING_CHUNK = "embedding_chunk"

_KNOWN_ORIGINS = {
    ORIGIN_API,
    ORIGIN_HTML_FALLBACK,
    ORIGIN_INTERNAL_LINK,
}

_ORIGIN_ALIASES = {
    "api": ORIGIN_API,
    "mediawiki_api": ORIGIN_API,
    "html_fallback": ORIGIN_HTML_FALLBACK,
    "html": ORIGIN_HTML_FALLBACK,
    "html_dom": ORIGIN_HTML_FALLBACK,
    "internal_link": ORIGIN_INTERNAL_LINK,
}


def _normalize_source_name(source_name: Optional[str]) -> str:
    return str(source_name or "").strip()


@dataclass(frozen=True)
class SourceDescriptor:
    source_name: str
    status: str
    source_role: str = SOURCE_ROLE
    schema_version: str = SOURCE_SCHEMA_VERSION

    @property
    def is_active(self) -> bool:
        return self.status == SOURCE_STATUS_ACTIVE

    @property
    def is_disabled(self) -> bool:
        return self.status == SOURCE_STATUS_DISABLED

    @property
    def is_known(self) -> bool:
        return self.source_name in SOURCE_REGISTRY


def get_source_status(source_name: Optional[str]) -> str:
    normalized = _normalize_source_name(source_name)
    return str(SOURCE_REGISTRY.get(normalized, "unknown")).strip() or "unknown"


def is_active_source(source_name: Optional[str]) -> bool:
    return get_source_status(source_name) == SOURCE_STATUS_ACTIVE


def list_registered_sources() -> List[str]:
    return list(SOURCE_REGISTRY.keys())


def list_formally_integrated_sources() -> List[str]:
    return list(FORMALLY_INTEGRATED_SOURCES.keys())


def get_source_registry_view() -> List[Dict[str, str]]:
    return [
        {
            "source_name": source_name,
            "status": status,
            "is_active": status == SOURCE_STATUS_ACTIVE,
        }
        for source_name, status in SOURCE_REGISTRY.items()
    ]


def get_formal_source_registration(source_name: Optional[str]) -> Dict[str, object]:
    normalized = _normalize_source_name(source_name)
    payload = dict(FORMALLY_INTEGRATED_SOURCES.get(normalized, {}))
    return {
        "source_name": normalized,
        "registry_status": get_source_status(normalized),
        "is_active": is_active_source(normalized),
        "is_formally_integrated": bool(payload),
        "formal_status": str(payload.get("formal_status", "")).strip(),
        "materialization_status": str(payload.get("materialization_status", "")).strip(),
        "cutover_ready": bool(payload.get("cutover_ready", False)),
        "approval_mode": str(payload.get("approval_mode", "")).strip(),
        "release_phase": str(payload.get("release_phase", "")).strip(),
    }


def source_is_formally_integrated(source_name: Optional[str]) -> bool:
    return bool(get_formal_source_registration(source_name)["is_formally_integrated"])


def get_source_schema_version(source_name: Optional[str]) -> str:
    normalized = _normalize_source_name(source_name)
    if not normalized or normalized == ACTIVE_SOURCE:
        return SOURCE_SCHEMA_VERSION
    return f"{normalized}_shadow_ready_v1"


def get_source_descriptor(source_name: Optional[str]) -> SourceDescriptor:
    normalized = _normalize_source_name(source_name)
    return SourceDescriptor(
        source_name=normalized,
        status=get_source_status(normalized),
        schema_version=get_source_schema_version(normalized),
    )


def get_source_descriptors() -> List[SourceDescriptor]:
    return [get_source_descriptor(source_name) for source_name in SOURCE_REGISTRY]


def get_source_descriptor_record(source_name: Optional[str]) -> Dict[str, str]:
    descriptor = get_source_descriptor(source_name)
    registration = get_formal_source_registration(source_name)
    return {
        "source_name": descriptor.source_name,
        "status": descriptor.status,
        "source_role": descriptor.source_role,
        "schema_version": descriptor.schema_version,
        "is_active": descriptor.is_active,
        "is_disabled": descriptor.is_disabled,
        "is_known": descriptor.is_known,
        "is_formally_integrated": registration["is_formally_integrated"],
        "formal_status": registration["formal_status"],
        "materialization_status": registration["materialization_status"],
        "cutover_ready": registration["cutover_ready"],
        "approval_mode": registration["approval_mode"],
        "release_phase": registration["release_phase"],
    }


def get_active_source() -> str:
    return ACTIVE_SOURCE


def get_active_source_record() -> Dict[str, str]:
    return {
        "source_name": ACTIVE_SOURCE,
        "status": get_source_status(ACTIVE_SOURCE),
        "source_role": SOURCE_ROLE,
        "schema_version": get_source_schema_version(ACTIVE_SOURCE),
        "is_active": True,
        "is_disabled": False,
        "is_known": True,
    }


def get_source_namespace(source_name: Optional[str]) -> str:
    normalized = _normalize_source_name(source_name)
    return normalized or ACTIVE_SOURCE


def get_source_storage_namespace(source_name: Optional[str]) -> str:
    return get_source_namespace(source_name)


def get_source_path_segment(source_name: Optional[str]) -> str:
    namespace = get_source_namespace(source_name)
    return namespace.replace(os.sep, "_").replace("/", "_").replace("\\", "_")


def get_source_namespace_dir(base_dir: str, source_name: Optional[str]) -> str:
    normalized = _normalize_source_name(source_name)
    if not normalized or normalized == ACTIVE_SOURCE:
        return base_dir
    return os.path.join(base_dir, get_source_path_segment(normalized))


def get_source_namespace_artifact_path(base_dir: str, source_name: Optional[str], filename: str) -> str:
    return os.path.join(get_source_namespace_dir(base_dir, source_name), filename)


def get_single_source_baseline_namespace() -> str:
    return ACTIVE_SOURCE


def get_single_source_baseline_namespace_dir(base_dir: str) -> str:
    return get_source_namespace_dir(base_dir, ACTIVE_SOURCE)


def normalize_origin(origin: Optional[str], default: str = ORIGIN_API) -> str:
    value = str(origin or "").strip().lower()
    if not value:
        return default
    return _ORIGIN_ALIASES.get(value, default)


def normalize_fetch_source(fetch_source: Optional[str], default: str = "html_dom") -> str:
    value = str(fetch_source or "").strip().lower()
    if value == "mediawiki_api":
        return "mediawiki_api"
    if value in {"html_dom", "html", "html_fallback"}:
        return "html_dom"
    return default


def normalize_source_filter(
    source_filter: Optional[Iterable[str]] = None,
    fallback_source: Optional[str] = None,
) -> List[str]:
    if source_filter is None:
        fallback = _normalize_source_name(fallback_source)
        if fallback:
            return [fallback]
        return list(DEFAULT_SOURCE_FILTER)
    if isinstance(source_filter, str):
        source_filter = [source_filter]

    normalized = []
    for item in source_filter:
        value = str(item or "").strip()
        if value and value not in normalized:
            normalized.append(value)
    if normalized:
        return normalized
    fallback = _normalize_source_name(fallback_source)
    if fallback:
        return [fallback]
    return list(DEFAULT_SOURCE_FILTER)


def is_known_source(source_name: Optional[str]) -> bool:
    return _normalize_source_name(source_name) in SOURCE_REGISTRY


def ensure_known_source(source_name: Optional[str]) -> None:
    normalized = _normalize_source_name(source_name)
    if not normalized or normalized not in SOURCE_REGISTRY:
        raise KeyError(f"Unknown source '{normalized or source_name}'")


def source_is_allowed_for_current_baseline(source_name: Optional[str]) -> bool:
    normalized = _normalize_source_name(source_name)
    return bool(normalized) and normalized == ACTIVE_SOURCE


def build_record_metadata(
    origin: Optional[str],
    record_type: str,
    *,
    source_name: Optional[str] = None,
    source_role: Optional[str] = None,
    source_title: str = "",
    extra: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    resolved_source = _normalize_source_name(source_name) or ACTIVE_SOURCE
    resolved_role = str(source_role or SOURCE_ROLE).strip() or SOURCE_ROLE
    metadata = {
        "source": resolved_source,
        "source_name": resolved_source,
        "source_role": resolved_role,
        "origin": normalize_origin(origin),
        "type": record_type,
    }
    metadata["schema_version"] = get_source_schema_version(resolved_source)
    if source_title:
        metadata["source_title"] = str(source_title).strip()
    if extra:
        for key, value in extra.items():
            if value is not None:
                metadata[key] = value
    return metadata


def apply_record_metadata(
    record: Optional[dict],
    origin: Optional[str],
    record_type: str,
    *,
    source_name: Optional[str] = None,
    source_role: Optional[str] = None,
    source_title: str = "",
    extra: Optional[Dict[str, str]] = None,
) -> dict:
    normalized = dict(record or {})
    normalized.update(
        build_record_metadata(
            origin,
            record_type,
            source_name=source_name,
            source_role=source_role,
            source_title=source_title,
            extra=extra,
        )
    )
    return normalized


class FutureSourceAdapterStub:
    """未来多源扩展预留；当前不允许启用 disabled source。"""

    def __init__(self, source_name: str):
        self.source_name = str(source_name or "").strip()
        self.status = SOURCE_REGISTRY.get(self.source_name, "unknown")

    def ensure_available(self) -> None:
        if self.status != "active":
            raise NotImplementedError(
                f"Source '{self.source_name}' is registered as '{self.status}' "
                "and cannot be used by the current single-source crawler."
            )


def get_future_source_stub(source_name: str) -> FutureSourceAdapterStub:
    return FutureSourceAdapterStub(source_name)

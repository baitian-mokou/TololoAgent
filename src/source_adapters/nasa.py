from __future__ import annotations

import glob
import os
import re
import urllib.request
from html import unescape
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.source_adapters.base import SourceAdapter, dump_json, load_json, list_namespace_files
from src.source_quality.value_normalizer import normalize_value
from src.source_control import SOURCE_ROLE


NASA_FACT_SHEETS = {
    "火星": {
        "title": "火星",
        "url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
        "record_id": "nasa-nssdc-mars-fact-sheet",
    },
    "Mars": {
        "title": "火星",
        "url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
        "record_id": "nasa-nssdc-mars-fact-sheet",
    },
}
NASA_LICENSE_HINT = "Public domain / NASA content usage guidelines"
NASA_MARS_FACT_FALLBACKS = (
    ("HAS_MASS", "6.4171e23 kg", "kg"),
    ("HAS_RADIUS", "3389.5 km", "km"),
    ("HAS_ATMOSPHERE", "carbon dioxide; nitrogen; argon", ""),
)
SATELLITE_SYSTEM_MAP = {
    "地球": "地球系统",
    "火星": "火星系统",
    "木星": "木星系统",
    "土星": "土星系统",
    "天王星": "天王星系统",
    "海王星": "海王星系统",
    "冥王星": "冥王星系统",
}
NATURAL_SATELLITES = {
    "月球",
    "火卫一",
    "火卫二",
    "木卫一",
    "木卫二",
    "木卫三",
    "木卫四",
    "土卫六",
    "土卫二",
    "海卫一",
    "冥卫一",
}
NASA_MARS_STRICT_TABLE_FALLBACK_HTML = """
<table>
  <tr><th>Field</th><th>Mars</th></tr>
  <tr><td>Mass (10^24 kg)</td><td>0.64171</td></tr>
  <tr><td>Mean radius (km)</td><td>3389.5</td></tr>
  <tr><td>Atmospheric composition</td><td>Carbon dioxide; Nitrogen; Argon</td></tr>
  <tr><td>Distance from Sun (10^6 km)</td><td>227.9</td></tr>
</table>
"""


class NasaPipelineAdapter(SourceAdapter):
    source_name = "nasa"
    origin = "html_fallback"
    materialization_mode = "offline_nasa_raw_pipeline_v1"
    cutover_ready = False
    source_purpose = "authoritative_fact_verification_and_numeric_supplement"

    def __init__(self, *, entity: str = "火星", timeout: int = 10, **kwargs):
        super().__init__(**kwargs)
        self.entity = entity
        self.timeout = timeout

    def fetch_or_load_raw(self) -> Dict[str, Any]:
        return self.fetch_offline()

    def fetch_offline(self) -> Dict[str, Any]:
        raw_files = sorted(glob.glob(os.path.join(self.raw_dir, "*_html.json")))
        if not raw_files:
            raise RuntimeError(f"No NASA raw json files found under {self.raw_dir}")
        return {
            "raw_files": raw_files,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def fetch_live(self) -> Dict[str, Any]:
        target = NASA_FACT_SHEETS.get(self.entity) or NASA_FACT_SHEETS["火星"]
        request = urllib.request.Request(
            target["url"],
            headers={"User-Agent": "tololo-source-preview/1.0 (offline-safe preview)"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            html = response.read().decode("utf-8", errors="replace")
        live_fetch_note = ""
        if not has_strict_fact_sheet_fields(html) and target["title"] == "火星":
            html = NASA_MARS_STRICT_TABLE_FALLBACK_HTML
            live_fetch_note = "primary NASA URL returned no strict fact-sheet rows; used bundled Mars strict-table preview fallback"
        return {
            "title": target["title"],
            "source_record_id": target["record_id"],
            "source_url": target["url"],
            "html": html,
            "live_fetch_note": live_fetch_note,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def normalize_records(self, raw_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        if "html" in raw_payload:
            return [self._record_from_fact_sheet(raw_payload)]
        records = []
        for path in raw_payload.get("raw_files", []):
            try:
                payload = load_json(path)
            except Exception:
                continue
            records.append(self._record_from_offline_raw(payload, raw_payload.get("fetched_at", "")))
        return [record for record in records if record.get("triples") or record.get("narratives")]

    def materialize(self, output_path: str, mode: str = None) -> Dict[str, Any]:
        if mode is not None:
            self.mode = self._normalize_mode(mode)
        if self.mode != "offline":
            return super().materialize(output_path, mode=self.mode)

        fetch_status = {
            "requested_mode": self.mode,
            "effective_mode": "offline",
            "status": "ok",
            "error": "",
            "payload": self.fetch_offline(),
        }
        raw_payload = fetch_status["payload"]
        records = self.normalize_records(raw_payload)
        summary = self.emit_records(records, write=True)
        metadata_audit = self.audit_metadata_contract()
        chroma = self.materialize_chroma()
        probes = self.probe()
        summary_path = os.path.join(self.triples_dir, "summary.json")
        report = {
            "source_name": self.source_name,
            "source_schema_version": self.schema_version,
            "source_role": SOURCE_ROLE,
            "namespace_status": "shadow_only",
            "source_purpose": self.source_purpose,
            "mode": self.mode,
            "materialization_mode": self.materialization_mode,
            "cutover_ready": False,
            "raw_dir": self.raw_dir,
            "triples_dir": self.triples_dir,
            "raw_files": [
                {"path": path, "title": self._read_raw_title(path)}
                for path in raw_payload["raw_files"]
            ],
            "triple_files": list_namespace_files(self.triples_dir, "_triples.json"),
            "narrative_files": list_namespace_files(self.triples_dir, "_narratives.json"),
            "pipeline": {
                "total_triples": summary.get("total_triples", 0),
                "total_narratives": summary.get("total_narratives", 0),
                "summary_exists": os.path.exists(summary_path),
                "summary": load_json(summary_path) if os.path.exists(summary_path) else {},
            },
            "metadata_contract": metadata_audit,
            "graph": {"skipped": True, "reason": "nasa_shadow_does_not_enable_multisource_graph_fusion"},
            "chroma": chroma,
            "probes": probes,
            "readiness_gate": {
                "passed": bool(metadata_audit["passed"]),
                "cutover_ready": False,
                "reason": "NASA is retained as shadow-only fact supplement; gate success is not active-source authorization",
            },
            "materialization": {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "output_path": output_path,
            },
            "fetch": {
                key: value
                for key, value in fetch_status.items()
                if key != "payload"
            },
        }
        dump_json(output_path, report)
        return report

    @staticmethod
    def _read_raw_title(path: str) -> str:
        try:
            return str(load_json(path).get("title", ""))
        except Exception:
            return ""

    def extra_report_fields(self) -> Dict[str, Any]:
        return {
            "live_preview": {
                "target_entity": self.entity,
                "source_candidates": sorted(NASA_FACT_SHEETS.keys()),
                "license_hint": NASA_LICENSE_HINT,
            }
        }

    def _record_from_fact_sheet(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        title = str(payload.get("title") or self.entity or "NASA fact sheet").strip()
        html = str(payload.get("html") or "")
        fetched_at = str(payload.get("fetched_at") or datetime.now(timezone.utc).isoformat())
        triples = parse_nasa_fact_sheet_candidates(
            html,
            payload=payload,
            fetched_at=fetched_at,
            schema_version=self.schema_version,
        )
        if not triples and title == "火星":
            for relation, normalized_value, unit in NASA_MARS_FACT_FALLBACKS:
                triples.append(self._preview_fact(
                    payload,
                    relation,
                    "NASA Mars Fact Sheet preview fallback after table parsing found no candidate row",
                    normalized_value,
                    fetched_at,
                    table_field="fallback_static_candidate",
                ))
        atmosphere = next((item.get("object") for item in triples if item.get("relation") == "HAS_ATMOSPHERE"), "")
        narrative = {
            "section": "NASA live preview",
            "content": f"NASA live preview parsed {len(triples)} candidate facts from a public fact sheet for {title}.",
            "keywords": [title, "NASA", "fact sheet"],
        }
        if atmosphere:
            narrative = {
                "section": "大气",
                "content": f"{title} NASA fact sheet 记录的大气成分为 {atmosphere}，并解析出质量、半径等候选事实。",
                "keywords": [title, "NASA", "fact sheet", "大气"],
            }
        return {
            "title": title,
            "triples": triples,
            "narratives": [narrative],
        }

    def _record_from_offline_raw(self, payload: Dict[str, Any], fetched_at: str) -> Dict[str, Any]:
        title = str(payload.get("title") or self.entity or "").strip()
        source_url = str(payload.get("url") or NASA_FACT_SHEETS["火星"]["url"])
        source_record_id = f"offline:{title or os.path.basename(source_url)}"
        html = str(payload.get("html") or "")
        text = str(payload.get("text") or payload.get("raw_text") or (html_to_text(html) if html else ""))
        triples = []
        if html:
            triples.extend(
                fact
                for fact in parse_nasa_fact_sheet_candidates(
                    html,
                    payload={"source_url": source_url, "source_record_id": source_record_id},
                    fetched_at=fetched_at or str(payload.get("crawl_time") or ""),
                    schema_version=self.schema_version,
                )
                if not fact.get("relation_semantics_warning")
            )
        if not any(item.get("relation") == "HAS_ATMOSPHERE" for item in triples):
            if "二氧化碳" in text or "氮气" in text or "氩气" in text:
                raw_value = "二氧化碳;氮气;氩气"
                triples.append(self._preview_fact(
                    {"source_url": source_url, "source_record_id": source_record_id},
                    "HAS_ATMOSPHERE",
                    raw_value,
                    raw_value,
                    fetched_at or str(payload.get("crawl_time") or ""),
                    table_field="offline_raw_text",
                ))
        orbit_host = self._extract_orbit_host(title, text)
        if orbit_host and not any(item.get("relation") == "ORBITS" for item in triples):
            triples.append(self._text_fact(
                source_url=source_url,
                source_record_id=source_record_id,
                relation="ORBITS",
                obj=orbit_host,
                fetched_at=fetched_at or str(payload.get("crawl_time") or ""),
                field_id="offline_orbit_text",
            ))
        if title in NATURAL_SATELLITES and orbit_host and not any(item.get("relation") == "PART_OF" for item in triples):
            triples.append(self._text_fact(
                source_url=source_url,
                source_record_id=source_record_id,
                relation="PART_OF",
                obj=SATELLITE_SYSTEM_MAP.get(orbit_host, f"{orbit_host}系统"),
                fetched_at=fetched_at or str(payload.get("crawl_time") or ""),
                field_id="offline_system_text",
            ))
        return {
            "title": title,
            "triples": triples,
            "narratives": [{
                "section": self._infer_section(text),
                "content": text[:300],
                "keywords": self._keywords_for_text(title, text),
            }] if text else [],
        }

    def _preview_fact(
        self,
        payload: Dict[str, Any],
        relation: str,
        raw_value: str,
        normalized_value: str,
        fetched_at: str,
        table_field: str = "",
    ) -> Dict[str, Any]:
        normalized = normalize_value(normalized_value or raw_value, relation)
        base_id = str(payload.get("source_record_id", "") or "nasa-preview")
        record_id = f"{base_id}:{table_field}" if table_field else base_id
        display_value = canonical_fact_object(normalized["normalized_value"], normalized["normalized_unit"])
        return {
            "relation": relation,
            "object": display_value,
            "source_record_id": record_id,
            "table_field": table_field,
            "source_url": payload.get("source_url", ""),
            "source_license": NASA_LICENSE_HINT,
            "license_hint": NASA_LICENSE_HINT,
            "fetched_at": fetched_at,
            "raw_value": raw_value,
            "normalized_value": normalized["normalized_value"],
            "unit": normalized["normalized_unit"],
            "confidence": max(0.65, float(normalized["confidence"])),
            "parse_status": normalized["parse_status"],
            "schema_version": self.schema_version,
            "source_name": self.source_name,
        }

    @staticmethod
    def _extract_orbit_host(title: str, text: str) -> str:
        clean_text = re.sub(r"\s+", "", str(text or ""))
        for pattern in (
            rf"{re.escape(title)}(?:绕|围绕)([\u4e00-\u9fffA-Za-z0-9·\-]+?)(?:公转|运行)",
            rf"{re.escape(title)}是([\u4e00-\u9fffA-Za-z0-9·\-]+?)的天然卫星",
        ):
            match = re.search(pattern, clean_text)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _infer_section(text: str) -> str:
        value = str(text or "")
        if any(token in value for token in ("大气", "气压", "二氧化碳", "氮气", "氧气", "甲烷")):
            return "大气"
        if any(token in value for token in ("绕", "公转", "轨道", "卫星", "探测器")):
            return "轨道"
        return "概要"

    @staticmethod
    def _keywords_for_text(title: str, text: str) -> List[str]:
        keywords = [title, "NASA"]
        for token in ("大气", "轨道", "卫星", "质量", "半径"):
            if token in str(text or "") and token not in keywords:
                keywords.append(token)
        return keywords

    def _text_fact(
        self,
        *,
        source_url: str,
        source_record_id: str,
        relation: str,
        obj: str,
        fetched_at: str,
        field_id: str,
    ) -> Dict[str, Any]:
        normalized = normalize_value(obj, relation)
        return {
            "relation": relation,
            "object": normalized["normalized_value"],
            "source_record_id": f"{source_record_id}:{field_id}",
            "table_field": field_id,
            "source_url": source_url,
            "source_license": NASA_LICENSE_HINT,
            "license_hint": NASA_LICENSE_HINT,
            "fetched_at": fetched_at,
            "raw_value": obj,
            "normalized_value": normalized["normalized_value"],
            "unit": normalized["normalized_unit"],
            "confidence": max(0.75, float(normalized["confidence"])),
            "parse_status": normalized["parse_status"],
            "schema_version": self.schema_version,
            "source_name": self.source_name,
        }


def html_to_text(html: str) -> str:
    without_noise = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_noise)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def extract_fact_sheet_table_values(html: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.IGNORECASE | re.DOTALL)
        cleaned = [html_to_text(cell) for cell in cells]
        cleaned = [cell for cell in cleaned if cell]
        if len(cleaned) >= 2:
            label = re.sub(r"\s+", " ", cleaned[0]).strip().lower()
            values[label] = cleaned[1]
    return values


def extract_fact_sheet_table_rows(html: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.IGNORECASE | re.DOTALL)
        cleaned = [html_to_text(cell) for cell in cells]
        cleaned = [cell for cell in cleaned if cell]
        if len(cleaned) >= 2:
            rows.append({"field": cleaned[0], "value": cleaned[1]})
    return rows


def parse_nasa_fact_sheet_candidates(
    html: str,
    *,
    payload: Dict[str, Any],
    fetched_at: str,
    schema_version: str,
) -> List[Dict[str, Any]]:
    rows = extract_fact_sheet_table_rows(html)
    triples: List[Dict[str, Any]] = []
    for field_names, relation in (
        (("mass",), "HAS_MASS"),
        (("mean radius", "vol. mean radius", "volumetric mean radius", "equatorial radius"), "HAS_RADIUS"),
        (("atmospheric composition", "atmosphere composition", "atmosphere"), "HAS_ATMOSPHERE"),
    ):
        row = find_table_row(rows, field_names)
        if row:
            raw_value = value_with_unit_hint(row["value"], row["field"], relation)
            triples.append(build_preview_fact(
                payload=payload,
                relation=relation,
                raw_value=raw_value,
                fetched_at=fetched_at,
                table_field=row["field"],
                schema_version=schema_version,
            ))
    orbit_row = find_table_row(rows, ("distance from sun", "semimajor axis", "semi-major axis"))
    if orbit_row:
        orbit_hint = build_preview_fact(
            payload=payload,
            relation="ORBITS",
            raw_value="Sun",
            fetched_at=fetched_at,
            table_field=orbit_row["field"],
            schema_version=schema_version,
        )
        orbit_hint["derived"] = True
        orbit_hint["derived_from"] = orbit_row["field"]
        orbit_hint["relation_semantics_warning"] = True
        orbit_hint["warning_reason"] = "Distance from Sun is an orbital-distance field, not a direct ORBITS ontology assertion."
        triples.append(orbit_hint)
    return triples


def has_strict_fact_sheet_fields(html: str) -> bool:
    rows = extract_fact_sheet_table_rows(html)
    required = (
        ("mass",),
        ("mean radius", "vol. mean radius", "volumetric mean radius", "equatorial radius"),
    )
    return all(bool(find_table_row(rows, names)) for names in required)


def build_preview_fact(
    *,
    payload: Dict[str, Any],
    relation: str,
    raw_value: str,
    fetched_at: str,
    table_field: str,
    schema_version: str,
) -> Dict[str, Any]:
    normalized = normalize_value(raw_value, relation)
    base_id = str(payload.get("source_record_id", "") or "nasa-preview")
    display_value = canonical_fact_object(normalized["normalized_value"], normalized["normalized_unit"])
    return {
        "relation": relation,
        "object": display_value,
        "source_record_id": f"{base_id}:{safe_field_id(table_field)}",
        "table_field": table_field,
        "source_url": payload.get("source_url", ""),
        "source_license": NASA_LICENSE_HINT,
        "license_hint": NASA_LICENSE_HINT,
        "fetched_at": fetched_at,
        "raw_value": raw_value,
        "normalized_value": normalized["normalized_value"],
        "unit": normalized["normalized_unit"],
        "confidence": normalized["confidence"],
        "parse_status": normalized["parse_status"],
        "schema_version": schema_version,
        "source_name": "nasa",
    }


def find_table_row(rows: List[Dict[str, str]], field_names: tuple[str, ...]) -> Dict[str, str]:
    for row in rows:
        field = row["field"].lower()
        if any(name in field for name in field_names):
            return row
    return {}


def value_with_unit_hint(value: str, field: str, relation: str) -> str:
    field_text = field.lower()
    raw = str(value or "").strip()
    if relation == "HAS_MASS":
        if "10^24" in field_text or "10 24" in field_text:
            return f"{raw}e24 kg"
        if "kg" in field_text and "kg" not in raw.lower():
            return f"{raw} kg"
    if relation == "HAS_RADIUS":
        if ("km" in field_text or "kilometer" in field_text) and "km" not in raw.lower():
            return f"{raw} km"
        if re.search(r"\bm\b|meter|metre", field_text) and not re.search(r"\bkm\b", field_text) and not re.search(r"\bm\b|米", raw.lower()):
            return f"{raw} m"
    return raw


def safe_field_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized or "field"


def extract_fact_sheet_value(text: str, label: str) -> str:
    pattern = rf"{re.escape(label)}\s*(?:\([^)]+\))?\s*([^\n\r<]+?)(?=\s+[A-Z][A-Za-z /()-]{{2,}}\s|$)"
    match = re.search(pattern, text)
    if not match:
        return ""
    return match.group(1).strip(" :;")


def normalize_nasa_value(raw_value: str, default_unit: str) -> str:
    value = re.sub(r"\s+", " ", str(raw_value or "")).strip()
    if default_unit and default_unit not in value:
        return f"{value} {default_unit}".strip()
    return value


def canonical_fact_object(normalized_value: str, normalized_unit: str) -> str:
    value = str(normalized_value or "").strip().replace("e+", "e")
    unit = str(normalized_unit or "").strip()
    if not unit or unit == "component_set":
        return value
    if value.endswith(f" {unit}") or value.endswith(unit):
        return value
    return f"{value} {unit}".strip()

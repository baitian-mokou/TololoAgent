from __future__ import annotations

import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.source_adapters.base import SourceAdapter, dump_json, load_json


WIKIDATA_ENTITY_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/{qid}"
WIKIDATA_LICENSE_HINT = "CC0-1.0"

PROPERTY_RELATION_MAP = {
    "P397": "ORBITS",
    "P2067": "HAS_MASS",
    "P2120": "HAS_RADIUS",
    "P523": "HAS_ATMOSPHERE",
    "P61": "DISCOVERED_BY",
    "P276": "LOCATED_IN",
    "P361": "PART_OF",
}


class WikidataFixtureAdapter(SourceAdapter):
    source_name = "wikidata"
    origin = "api"
    materialization_mode = "offline_wikidata_fixture_v1"
    cutover_ready = False

    def __init__(self, *, fixture_path: str = None, entity: str = "火星", timeout: int = 10, **kwargs):
        super().__init__(**kwargs)
        self.entity = entity
        self.timeout = timeout
        self.fixture_path = fixture_path or os.path.join(
            self.base_dir,
            "data",
            "source_fixtures",
            "wikidata",
            "solar_system_fixture.json",
        )
        self.raw_copy_status = {"written": False, "path": "", "error": ""}

    def fetch_or_load_raw(self) -> Dict[str, Any]:
        return self.fetch_offline()

    def fetch_offline(self) -> Dict[str, Any]:
        payload = load_json(self.fixture_path)
        raw_copy_path = os.path.join(self.raw_dir, "solar_system_fixture.json")
        self.raw_copy_status = {"written": False, "path": raw_copy_path, "error": ""}
        if self.writes_official_namespace:
            try:
                dump_json(raw_copy_path, payload)
                self.raw_copy_status["written"] = True
            except OSError as exc:
                self.raw_copy_status["error"] = str(exc)
        return payload

    def fetch_live(self) -> Dict[str, Any]:
        qid = self._resolve_qid(self.entity)
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": qid,
            "props": "labels|claims",
            "languages": "zh|zh-hans|en",
        }
        payload = self._get_json(params)
        payload["preview_target"] = {"entity": self.entity, "qid": qid}
        payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
        return payload

    def normalize_records(self, raw_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        if "entities" in raw_payload:
            return self._normalize_live_entities(raw_payload)
        records = raw_payload.get("records", [])
        if not isinstance(records, list):
            raise ValueError("Wikidata fixture must contain a records list")
        return records

    def extra_report_fields(self) -> Dict[str, Any]:
        return {
            "raw_copy_status": self.raw_copy_status,
            "live_preview": {
                "target_entity": self.entity,
                "supported_relations": sorted(set(PROPERTY_RELATION_MAP.values())),
                "api": WIKIDATA_ENTITY_API,
                "license_hint": WIKIDATA_LICENSE_HINT,
            },
        }

    def _resolve_qid(self, entity: str) -> str:
        value = str(entity or "").strip()
        if value.upper().startswith("Q") and value[1:].isdigit():
            return value.upper()
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "language": "zh",
            "uselang": "zh",
            "search": value,
            "limit": "1",
        }
        payload = self._get_json(params)
        search = payload.get("search", [])
        if not search:
            raise RuntimeError(f"Wikidata entity not found for '{value}'")
        return str(search[0].get("id") or "").strip()

    def _get_json(self, params: Dict[str, str]) -> Dict[str, Any]:
        url = f"{WIKIDATA_ENTITY_API}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "tololo-source-preview/1.0 (offline-safe preview)"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return load_json_from_bytes(response.read())

    def _normalize_live_entities(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        entities = payload.get("entities", {})
        fetched_at = str(payload.get("fetched_at") or datetime.now(timezone.utc).isoformat())
        records = []
        for qid, entity in entities.items():
            labels = entity.get("labels", {})
            title = (
                labels.get("zh-hans", {}).get("value")
                or labels.get("zh", {}).get("value")
                or labels.get("en", {}).get("value")
                or qid
            )
            triples = []
            for property_id, relation in PROPERTY_RELATION_MAP.items():
                for claim in entity.get("claims", {}).get(property_id, []):
                    fact = self._claim_to_fact(qid, relation, property_id, claim, fetched_at)
                    if fact:
                        triples.append(fact)
            records.append({
                "title": title,
                "qid": qid,
                "triples": triples,
                "narratives": [{
                    "section": "Wikidata live preview",
                    "content": f"Wikidata live preview parsed {len(triples)} candidate facts for {title}.",
                    "keywords": [title, qid, "Wikidata"],
                }],
            })
        return records

    def _claim_to_fact(
        self,
        qid: str,
        relation: str,
        property_id: str,
        claim: Dict[str, Any],
        fetched_at: str,
    ) -> Dict[str, Any]:
        mainsnak = claim.get("mainsnak", {})
        datavalue = mainsnak.get("datavalue", {})
        raw_value = datavalue.get("value")
        normalized_value, unit = normalize_wikidata_value(raw_value)
        if normalized_value == "":
            return {}
        return {
            "relation": relation,
            "object": normalized_value,
            "property_id": property_id,
            "source_record_id": f"{qid}:{property_id}:{claim.get('id', '')}",
            "source_url": WIKIDATA_ENTITY_URL.format(qid=qid),
            "source_license": WIKIDATA_LICENSE_HINT,
            "license_hint": WIKIDATA_LICENSE_HINT,
            "fetched_at": fetched_at,
            "raw_value": raw_value,
            "normalized_value": normalized_value,
            "unit": unit,
            "confidence": 0.85,
        }


def load_json_from_bytes(payload: bytes) -> Dict[str, Any]:
    import json

    return json.loads(payload.decode("utf-8"))


def normalize_wikidata_value(raw_value: Any) -> tuple[str, str]:
    if isinstance(raw_value, dict):
        if "amount" in raw_value:
            amount = str(raw_value.get("amount", "")).lstrip("+")
            unit_url = str(raw_value.get("unit", "") or "")
            unit = unit_url.rsplit("/", 1)[-1] if unit_url and unit_url != "1" else ""
            return (" ".join(item for item in [amount, unit] if item), unit)
        if "id" in raw_value:
            return str(raw_value.get("id") or ""), ""
        if "text" in raw_value:
            return str(raw_value.get("text") or ""), ""
        if "time" in raw_value:
            return str(raw_value.get("time") or ""), ""
    if raw_value is None:
        return "", ""
    return str(raw_value), ""

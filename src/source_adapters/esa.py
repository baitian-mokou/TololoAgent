from __future__ import annotations

import os
from typing import Any, Dict, List

from src.source_adapters.base import SourceAdapter, dump_json, load_json


class EsaSmokeAdapter(SourceAdapter):
    source_name = "esa"
    origin = "html_fallback"
    materialization_mode = "offline_esa_smoke_fixture_v1"
    cutover_ready = False

    def __init__(self, *, fixture_path: str = None, **kwargs):
        super().__init__(**kwargs)
        self.fixture_path = fixture_path or os.path.join(
            self.base_dir,
            "data",
            "source_fixtures",
            "esa",
            "smoke_fixture.json",
        )
        self.raw_copy_status = {"written": False, "path": "", "error": ""}

    def fetch_or_load_raw(self) -> Dict[str, Any]:
        return self.fetch_offline()

    def fetch_offline(self) -> Dict[str, Any]:
        payload = load_json(self.fixture_path)
        raw_copy_path = os.path.join(self.raw_dir, "smoke_fixture.json")
        self.raw_copy_status = {"written": False, "path": raw_copy_path, "error": ""}
        if self.writes_official_namespace:
            try:
                dump_json(raw_copy_path, payload)
                self.raw_copy_status["written"] = True
            except OSError as exc:
                self.raw_copy_status["error"] = str(exc)
        return payload

    def fetch_live(self) -> Dict[str, Any]:
        raise NotImplementedError("ESA live preview is not implemented for the smoke adapter")

    def normalize_records(self, raw_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        records = raw_payload.get("records", [])
        if not isinstance(records, list):
            raise ValueError("ESA fixture must contain a records list")
        return records

    def extra_report_fields(self) -> Dict[str, Any]:
        return {"raw_copy_status": self.raw_copy_status}

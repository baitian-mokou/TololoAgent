from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_adapters.wikidata import PROPERTY_RELATION_MAP
from src.source_control import SOURCE_ROLE, apply_record_metadata, get_source_schema_version


RAW_ROOT = ROOT / "data" / "raw_json"
TRIPLES_ROOT = ROOT / "data" / "triples"
REPORT_DIR = ROOT / "evaluation" / "ingestion"
MIN_NARRATIVE_LENGTH = 20
MAX_CHUNK_CHARS = 900

FACT_SUBJECTS = {
    "mercuryfact": "Mercury",
    "venusfact": "Venus",
    "earthfact": "Earth",
    "moonfact": "Moon",
    "marsfact": "Mars",
    "jupiterfact": "Jupiter",
    "saturnfact": "Saturn",
    "uranusfact": "Uranus",
    "neptunefact": "Neptune",
}

MISSION_TARGETS = {
    "Mars": ("mars", "red planet"),
    "Jupiter": ("jupiter", "ganymede", "europa", "callisto", "juice"),
    "Mercury": ("mercury", "bepicolombo", "messenger"),
    "Venus": ("venus",),
    "Moon": ("moon", "lunar", "smart-1"),
    "Sun": ("solar orbiter", "sun"),
    "Comet": ("comet", "rosetta", "67p"),
    "Asteroid": ("asteroid", "bennu", "psyche", "osiris-rex"),
}
LOW_QUALITY_URL_TOKENS = (
    "?search",
    "search=",
    "/blogs/",
    "/stories/",
    "/resources/",
    "raw-images",
    "/image/",
    "/images/",
    "/gallery/",
    "/video/",
    "/videos/",
    "/media/",
)


class RawHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: List[str] = []
        self.text_parts: List[str] = []
        self.rows: List[List[str]] = []
        self._in_title = False
        self._skip_depth = 0
        self._current_row: List[str] | None = None
        self._current_cell: List[str] | None = None

    def handle_starttag(self, tag: str, attrs: Sequence[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._in_title = True
        if lowered in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if lowered == "tr":
            self._current_row = []
        if lowered in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._in_title = False
        if lowered in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if lowered in {"td", "th"} and self._current_row is not None and self._current_cell is not None:
            cell = clean_text(" ".join(self._current_cell))
            if cell:
                self._current_row.append(cell)
            self._current_cell = None
        if lowered == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if not text:
            return
        if self._current_cell is not None:
            self._current_cell.append(text)
        if self._in_title:
            self.title_parts.append(text)
        elif not self._skip_depth:
            self.text_parts.append(text)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", clean_text(value))
    return (cleaned.strip("._") or "record")[:120]


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_html(html: str) -> RawHtmlParser:
    parser = RawHtmlParser()
    parser.feed(html or "")
    return parser


def raw_text_and_tables(raw: Dict[str, Any]) -> tuple[str, List[List[str]]]:
    text = clean_text(raw.get("text") or raw.get("raw_text") or "")
    rows: List[List[str]] = []
    html = str(raw.get("html") or "")
    if html:
        parser = parse_html(html)
        rows = parser.rows
        if not text:
            text = clean_text(" ".join(parser.text_parts))
    return text, rows


def source_url(raw: Dict[str, Any]) -> str:
    return clean_text(raw.get("source_url") or raw.get("url") or "")


def low_quality_raw(raw: Dict[str, Any]) -> bool:
    title = raw_title("raw", raw).lower()
    url = source_url(raw).lower()
    if "search results" in title:
        return True
    return any(token in url for token in LOW_QUALITY_URL_TOKENS)


def raw_title(source_name: str, raw: Dict[str, Any]) -> str:
    title = clean_text(raw.get("title") or raw.get("source_title") or raw.get("qid") or "")
    if not title and raw.get("html"):
        parser = parse_html(str(raw.get("html") or ""))
        title = clean_text(" ".join(parser.title_parts))
    return title or source_name


def subject_for_raw(source_name: str, raw: Dict[str, Any]) -> str:
    if source_name == "wikidata":
        return raw_title(source_name, raw)
    url = source_url(raw).lower()
    for token, subject in FACT_SUBJECTS.items():
        if token in url:
            return subject
    title = raw_title(source_name, raw)
    title = re.sub(r"^ESA\s*-\s*", "", title)
    title = re.sub(r"\s*-\s*NASA.*$", "", title)
    return title[:80]


def metadata(source_name: str, raw: Dict[str, Any], record_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    title = raw_title(source_name, raw)
    enriched = dict(payload)
    enriched.setdefault("source_url", source_url(raw))
    return apply_record_metadata(
        enriched,
        clean_text(raw.get("origin") or "manifest_raw"),
        record_type,
        source_name=source_name,
        source_role=SOURCE_ROLE,
        source_title=title,
    )


def narrative_chunks(source_name: str, raw: Dict[str, Any], text: str) -> List[Dict[str, Any]]:
    text = clean_text(text)
    if len(text) < MIN_NARRATIVE_LENGTH:
        return []
    title = raw_title(source_name, raw)
    chunks = []
    for index, start in enumerate(range(0, min(len(text), 3600), MAX_CHUNK_CHARS), start=1):
        chunk = text[start : start + MAX_CHUNK_CHARS].strip()
        if len(chunk) < MIN_NARRATIVE_LENGTH:
            continue
        chunks.append(
            metadata(
                source_name,
                raw,
                "embedding_chunk",
                {
                    "page_title": title,
                    "section": f"raw_chunk_{index}",
                    "content": chunk,
                    "keywords": [title, source_name],
                },
            )
        )
    return chunks


def table_triples(source_name: str, raw: Dict[str, Any], rows: Sequence[Sequence[str]]) -> List[Dict[str, Any]]:
    subject = subject_for_raw(source_name, raw)
    triples = []
    for row in rows:
        if len(row) < 2:
            continue
        field = clean_text(row[0])
        value = clean_text(row[1])
        lowered = field.lower()
        relation = ""
        obj = value
        if "mass" in lowered:
            relation = "HAS_MASS"
            if "10^24" in lowered or "10 24" in lowered:
                obj = f"{value} 10^24 kg"
        elif "mean radius" in lowered or lowered == "radius" or "radius (km)" in lowered:
            relation = "HAS_RADIUS"
            if re.fullmatch(r"[+-]?\d+(\.\d+)?", value):
                obj = f"{value} km"
        elif "diameter" in lowered:
            relation = "HAS_DIAMETER"
            if re.fullmatch(r"[+-]?\d+(\.\d+)?", value):
                obj = f"{value} km"
        elif "atmospheric composition" in lowered or "atmosphere" in lowered:
            relation = "HAS_ATMOSPHERE"
        if relation and obj and subject:
            triples.append(
                metadata(
                    source_name,
                    raw,
                    "triple_candidate",
                    {
                        "subject": subject,
                        "relation": relation,
                        "object": obj,
                        "source_field": field,
                        "raw": f"{field}: {value}",
                    },
                )
            )
    return triples


def mission_triples(source_name: str, raw: Dict[str, Any], text: str) -> List[Dict[str, Any]]:
    if source_name not in {"nasa", "esa"}:
        return []
    haystack = f"{raw_title(source_name, raw)} {source_url(raw)}".lower()
    if not any(token in haystack for token in ("mission", "spacecraft", "orbiter", "rover", "juice", "rosetta", "express")):
        return []
    subject = subject_for_raw(source_name, raw)
    operator = "NASA" if source_name == "nasa" else "ESA"
    triples = [
        metadata(
            source_name,
            raw,
            "triple_candidate",
            {
                "subject": subject,
                "relation": "OPERATED_BY",
                "object": operator,
                "source_field": "source_manifest",
                "raw": f"{subject} source={operator}",
            },
        )
    ]
    for target, tokens in MISSION_TARGETS.items():
        if any(token in haystack for token in tokens):
            triples.append(
                metadata(
                    source_name,
                    raw,
                    "triple_candidate",
                    {
                        "subject": subject,
                        "relation": "HAS_MISSION_TARGET",
                        "object": target,
                        "source_field": "text/url keyword",
                        "raw": target,
                    },
                )
            )
    return triples


def wikidata_label_from_entity(entity: Dict[str, Any], qid: str) -> str:
    labels = entity.get("labels", {})
    return clean_text(
        labels.get("zh-hans", {}).get("value")
        or labels.get("zh", {}).get("value")
        or labels.get("en", {}).get("value")
        or qid
    )


def wikidata_claim_value(value: Any) -> str:
    if isinstance(value, dict):
        if str(value.get("id") or "").upper().startswith("Q"):
            return str(value.get("id")).upper()
        amount = clean_text(value.get("amount") or "")
        unit = clean_text(str(value.get("unit") or "").rsplit("/", 1)[-1])
        if amount:
            return f"{amount.lstrip('+')} {unit}".strip()
    return clean_text(value)


def wikidata_triples(source_name: str, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    entity = raw.get("entity") if isinstance(raw.get("entity"), dict) else {}
    if not entity and isinstance(raw.get("entities"), dict):
        qid = clean_text(raw.get("qid") or next(iter(raw["entities"].keys()), ""))
        entity = raw["entities"].get(qid, {})
    qid = clean_text(raw.get("qid") or raw.get("source_record_id") or "")
    subject = wikidata_label_from_entity(entity, qid) if entity else raw_title(source_name, raw)
    triples = []
    for property_id, relation in PROPERTY_RELATION_MAP.items():
        for claim in entity.get("claims", {}).get(property_id, []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            obj = wikidata_claim_value(value)
            if not obj:
                continue
            triples.append(
                metadata(
                    source_name,
                    raw,
                    "triple_candidate",
                    {
                        "subject": subject,
                        "relation": relation,
                        "object": obj,
                        "property_id": property_id,
                        "source_field": property_id,
                        "raw": f"{property_id}: {obj}",
                    },
                )
            )
    return triples


def wikidata_text(raw: Dict[str, Any]) -> str:
    entity = raw.get("entity") if isinstance(raw.get("entity"), dict) else {}
    descriptions = entity.get("descriptions", {}) if entity else {}
    values = [item.get("value", "") for item in descriptions.values() if isinstance(item, dict)]
    return clean_text(raw.get("text") or " ".join(values))


def convert_raw_payload(source_name: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("pending_queue") is not None:
        return {"title": "", "triples": [], "narratives": []}
    if source_name in {"nasa", "esa"} and low_quality_raw(raw):
        return {"title": raw_title(source_name, raw), "triples": [], "narratives": []}
    if source_name == "wikidata" and isinstance(raw.get("entity"), dict):
        text = wikidata_text(raw)
        rows: List[List[str]] = []
    else:
        text, rows = raw_text_and_tables(raw)
    narratives = narrative_chunks(source_name, raw, text)
    triples = wikidata_triples(source_name, raw) if source_name == "wikidata" else table_triples(source_name, raw, rows)
    triples.extend(mission_triples(source_name, raw, text))
    return {
        "title": raw_title(source_name, raw),
        "source_url": source_url(raw),
        "triples": triples,
        "narratives": narratives,
    }


def raw_files_for(source_name: str, raw_root: Path, limit: int) -> List[Path]:
    files = [path for path in sorted((raw_root / source_name).glob("*.json")) if path.name != "__crawl_state__.json"]
    return files[:limit] if limit > 0 else files


def allowed_wikidata_qids() -> set[str]:
    path = ROOT / "evaluation" / "source_frontiers" / "wikidata_frontier.json"
    if not path.exists():
        return set()
    try:
        payload = read_json(path)
    except Exception:
        return set()
    return {
        clean_text(item.get("qid") or "").upper()
        for item in payload.get("accepted", [])
        if clean_text(item.get("qid") or "").upper().startswith("Q")
    }


def materialize_source(
    source_name: str,
    *,
    limit: int,
    raw_root: Path = RAW_ROOT,
    triples_root: Path = TRIPLES_ROOT,
    report_path: Path | None = None,
) -> Dict[str, Any]:
    out_dir = triples_root / source_name
    out_dir.mkdir(parents=True, exist_ok=True)
    wikidata_qids = allowed_wikidata_qids() if source_name == "wikidata" else set()
    raw_processed = triples_written = narratives_written = skipped_empty = failed = 0
    files_written = []
    errors = []

    for path in raw_files_for(source_name, raw_root, limit):
        try:
            raw_payload = read_json(path)
            if wikidata_qids:
                qid = clean_text(raw_payload.get("qid") or raw_payload.get("source_record_id") or "").upper()
                if not qid or qid not in wikidata_qids:
                    skipped_empty += 1
                    continue
            record = convert_raw_payload(source_name, raw_payload)
            raw_processed += 1
            title = record["title"] or path.stem
            if not record["triples"] and not record["narratives"]:
                skipped_empty += 1
                continue
            if record["triples"]:
                triple_path = out_dir / f"{safe_name(title)}_triples.json"
                write_json(triple_path, record["triples"])
                triples_written += len(record["triples"])
                files_written.append(str(triple_path))
            if record["narratives"]:
                narrative_path = out_dir / f"{safe_name(title)}_narratives.json"
                write_json(narrative_path, record["narratives"])
                narratives_written += len(record["narratives"])
                files_written.append(str(narrative_path))
        except Exception as exc:
            failed += 1
            errors.append({"path": str(path), "error": str(exc), "type": type(exc).__name__})

    summary = {
        "source": source_name,
        "source_name": source_name,
        "schema_version": get_source_schema_version(source_name),
        "mode": "manifest_raw_to_triples_narratives",
        "generated_at": utc_now(),
        "raw_processed": raw_processed,
        "triples_written": triples_written,
        "narratives_written": narratives_written,
        "skipped_empty": skipped_empty,
        "failed": failed,
        "files_written": files_written,
        "errors": errors,
    }
    write_json(out_dir / "summary.json", summary)
    write_json(report_path or REPORT_DIR / f"{source_name}_manifest_materialization_report.json", summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert manifest raw JSON into local triples and narratives without network.")
    parser.add_argument("--source", required=True, choices=("nasa", "esa", "wikidata"))
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--report-json", default="")
    args = parser.parse_args(argv)

    report = materialize_source(
        args.source,
        limit=args.limit,
        report_path=Path(args.report_json) if args.report_json else None,
    )
    print(
        f"{args.source}: raw={report['raw_processed']} triples={report['triples_written']} "
        f"narratives={report['narratives_written']} skipped_empty={report['skipped_empty']} failed={report['failed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

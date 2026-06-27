import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ACTIVE_SOURCE, RAW_JSON_DIR, SOURCE_REGISTRY, TRIPLES_DIR
from src.nlp.nlp_pipeline import NlpPipeline
from src.nlp.ontology import ALLOWED_RELATIONS, validate_triple
from src.nlp.text_normalizer import (
    normalize_narrative_record,
    normalize_to_simplified,
    normalize_triple_record,
)
from src.source_control import (
    SOURCE_ROLE,
    SOURCE_SCHEMA_VERSION,
    normalize_fetch_source,
    normalize_origin,
)


INVALID_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|？！：；，。、【】「」『』《》（）→←↑↓"\x27\u2019\u0305]')


def sanitize_title(name: str) -> str:
    value = normalize_to_simplified(name or "").strip()
    return INVALID_FILENAME_CHARS_RE.sub("_", value)


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def score_raw_record(record: dict) -> int:
    score = 0
    if normalize_fetch_source(record.get("fetch_source") or record.get("source")) == "mediawiki_api":
        score += 1000
    if record.get("html"):
        score += 200
    score += int(record.get("word_count_cn") or 0)
    score += min(int(record.get("content_length") or 0), 50000) // 20
    return score


def normalize_raw_record(record: dict, fallback_title: str) -> dict:
    normalized = dict(record or {})
    title = normalize_to_simplified(normalized.get("title") or fallback_title).strip()
    raw_text = normalized.get("raw_text") or normalized.get("text") or ""
    fetch_source = normalize_fetch_source(
        normalized.get("fetch_source")
        or normalized.get("origin")
        or normalized.get("source")
    )
    normalized["title"] = title
    normalized["source"] = ACTIVE_SOURCE
    normalized["source_role"] = SOURCE_ROLE
    normalized["origin"] = normalize_origin(normalized.get("origin") or fetch_source)
    normalized["fetch_source"] = fetch_source
    normalized["raw_text"] = raw_text
    normalized["text"] = raw_text
    normalized["content_length"] = len(raw_text)
    normalized["char_count"] = len(raw_text)
    if not normalized.get("word_count_cn"):
        normalized["word_count_cn"] = len(re.findall(r"[\u4e00-\u9fff]", raw_text))
    return normalized


def duplicate_groups(base_dir: str, suffix: str) -> int:
    groups = defaultdict(list)
    for fname in os.listdir(base_dir):
        if not fname.endswith(suffix):
            continue
        groups[normalize_to_simplified(fname[:-len(suffix)])].append(fname)
    return sum(1 for values in groups.values() if len(values) > 1)


def audit_state() -> dict:
    stats = {
        "raw_total": 0,
        "raw_bad_source": 0,
        "raw_missing_source_role": 0,
        "raw_missing_origin": 0,
        "raw_missing_fetch_source": 0,
        "raw_duplicate_groups": duplicate_groups(RAW_JSON_DIR, "_html.json"),
        "triple_files": 0,
        "triple_total": 0,
        "triple_invalid_relation": 0,
        "triple_validate_failed": 0,
        "triple_bad_source": 0,
        "triple_missing_source_role": 0,
        "triple_missing_origin": 0,
        "triple_duplicate_groups": duplicate_groups(TRIPLES_DIR, "_triples.json"),
        "narrative_files": 0,
        "narrative_total": 0,
        "narrative_bad_source": 0,
        "narrative_missing_source_role": 0,
        "narrative_missing_origin": 0,
        "narrative_duplicate_groups": duplicate_groups(TRIPLES_DIR, "_narratives.json"),
    }

    for fname in os.listdir(RAW_JSON_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(RAW_JSON_DIR, fname)
        try:
            record = load_json(path)
        except Exception:
            continue
        if not isinstance(record, dict):
            continue
        stats["raw_total"] += 1
        if record.get("source") != ACTIVE_SOURCE:
            stats["raw_bad_source"] += 1
        if not record.get("source_role"):
            stats["raw_missing_source_role"] += 1
        if not record.get("origin"):
            stats["raw_missing_origin"] += 1
        if not record.get("fetch_source"):
            stats["raw_missing_fetch_source"] += 1

    for fname in os.listdir(TRIPLES_DIR):
        path = os.path.join(TRIPLES_DIR, fname)
        if fname.endswith("_triples.json"):
            stats["triple_files"] += 1
            try:
                records = load_json(path)
            except Exception:
                continue
            if not isinstance(records, list):
                continue
            for record in records:
                normalized = normalize_triple_record(record)
                stats["triple_total"] += 1
                relation = normalize_to_simplified(str(normalized.get("relation", "")).strip())
                if relation not in ALLOWED_RELATIONS:
                    stats["triple_invalid_relation"] += 1
                if validate_triple(
                    normalized.get("subject", ""),
                    relation,
                    normalized.get("object", ""),
                ) is None:
                    stats["triple_validate_failed"] += 1
                if normalized.get("source") != ACTIVE_SOURCE:
                    stats["triple_bad_source"] += 1
                if not normalized.get("source_role"):
                    stats["triple_missing_source_role"] += 1
                if not normalized.get("origin"):
                    stats["triple_missing_origin"] += 1
        elif fname.endswith("_narratives.json"):
            stats["narrative_files"] += 1
            try:
                records = load_json(path)
            except Exception:
                continue
            if not isinstance(records, list):
                continue
            for record in records:
                normalized = normalize_narrative_record(record)
                stats["narrative_total"] += 1
                if normalized.get("source") != ACTIVE_SOURCE:
                    stats["narrative_bad_source"] += 1
                if not normalized.get("source_role"):
                    stats["narrative_missing_source_role"] += 1
                if not normalized.get("origin"):
                    stats["narrative_missing_origin"] += 1

    summary_path = os.path.join(TRIPLES_DIR, "summary.json")
    summary = load_json(summary_path) if os.path.exists(summary_path) else {}
    stats["summary_has_active_source"] = int("active_source" in summary)
    stats["summary_has_source_registry"] = int("source_registry" in summary)
    stats["summary_has_source_schema_version"] = int("source_schema_version" in summary)
    return stats


def normalize_raw_json_store() -> dict:
    grouped = defaultdict(list)
    for fname in os.listdir(RAW_JSON_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(RAW_JSON_DIR, fname)
        try:
            record = load_json(path)
        except Exception:
            continue
        if not isinstance(record, dict):
            continue
        fallback_title = fname[:-10] if fname.endswith("_html.json") else fname[:-5]
        normalized = normalize_raw_record(record, fallback_title)
        canonical_name = f"{sanitize_title(normalized['title'])}_html.json"
        grouped[canonical_name].append((fname, normalized))

    canonical_records = {}
    removed = []
    for canonical_name, items in grouped.items():
        best_name, best_record = max(items, key=lambda item: score_raw_record(item[1]))
        merged = dict(best_record)
        for _, candidate in items:
            if not merged.get("html") and candidate.get("html"):
                merged["html"] = candidate["html"]
            if not merged.get("raw_text") and candidate.get("raw_text"):
                merged["raw_text"] = candidate["raw_text"]
                merged["text"] = candidate["raw_text"]
        canonical_records[canonical_name] = merged
        for original_name, _ in items:
            if original_name != canonical_name:
                removed.append(original_name)
        if best_name != canonical_name and canonical_name not in removed:
            removed.append(best_name)

    existing_files = [fname for fname in os.listdir(RAW_JSON_DIR) if fname.endswith(".json")]
    for fname in existing_files:
        if fname not in canonical_records:
            os.remove(os.path.join(RAW_JSON_DIR, fname))

    for fname, record in canonical_records.items():
        dump_json(os.path.join(RAW_JSON_DIR, fname), record)

    return {
        "canonical_raw_files": len(canonical_records),
        "removed_raw_files": len(set(removed)),
    }


def clear_triple_outputs() -> dict:
    removed = 0
    for fname in os.listdir(TRIPLES_DIR):
        if fname.endswith("_triples.json") or fname.endswith("_narratives.json") or fname == "summary.json":
            os.remove(os.path.join(TRIPLES_DIR, fname))
            removed += 1
    return {"removed_triple_outputs": removed}


def rebuild_outputs() -> dict:
    pipeline = NlpPipeline()
    total_triples, total_narratives = pipeline.process_all()
    return {
        "rebuilt_total_triples": total_triples,
        "rebuilt_total_narratives": total_narratives,
    }


def main():
    before = audit_state()
    raw_result = normalize_raw_json_store()
    cleanup_result = clear_triple_outputs()
    rebuild_result = rebuild_outputs()
    after = audit_state()
    print(json.dumps({
        "before": before,
        "raw_result": raw_result,
        "cleanup_result": cleanup_result,
        "rebuild_result": rebuild_result,
        "after": after,
        "active_source": ACTIVE_SOURCE,
        "source_registry": SOURCE_REGISTRY,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

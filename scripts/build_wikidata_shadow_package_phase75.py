from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.materialize_manifest_raw_records import safe_name
from scripts.select_deduped_frontier_candidates import canonical_url, normalized_title


SOURCE_ID = "wikidata"
SCHEMA_VERSION = "wikidata_shadow_ready_v1"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return relative.parts[:2] == ("evaluation", "four_source_expansion") or (allow_docs and relative.parts[:1] == ("docs",))


def approval_payload(item_count: int) -> Dict[str, Any]:
    return {
        "source_id": SOURCE_ID,
        "approval_decision": "pending",
        "approved_item_count": 0,
        "max_available_item_count": item_count,
        "reviewer_notes": "",
        "allowed_output_scope": "data/triples_shadow/wikidata only after explicit guarded approval",
    }


def accepted_statuses(phase74_json: Path) -> List[Dict[str, Any]]:
    report = read_json(phase74_json)
    rows = report.get("candidate_statuses", []) if isinstance(report, dict) else []
    return [row for row in rows if row.get("status") == "accepted_for_package"]


def rejected_fingerprints(phase74_json: Path) -> tuple[set[str], set[str]]:
    report = read_json(phase74_json)
    urls: set[str] = set()
    titles: set[str] = set()
    for row in report.get("candidate_statuses", []) if isinstance(report, dict) else []:
        if row.get("status") == "accepted_for_package":
            continue
        url = canonical_url(str(row.get("url") or ""))
        title = normalized_title(str(row.get("title") or ""))
        if url:
            urls.add(url)
        if title:
            titles.add(title)
    return urls, titles


def raw_record(raw_path: Path) -> Dict[str, Any]:
    payload = read_json(raw_path)
    if not isinstance(payload, dict):
        return {}
    return payload.get("record", {}) if isinstance(payload.get("record"), dict) else payload


def materialized_pair(triples_root: Path, title: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    stem = safe_name(title)
    triples = read_json(triples_root / f"{stem}_triples.json")
    narratives = read_json(triples_root / f"{stem}_narratives.json")
    return (triples if isinstance(triples, list) else [], narratives if isinstance(narratives, list) else [])


def triples_from_raw(record: Dict[str, Any], url: str) -> List[Dict[str, Any]]:
    title = str(record.get("title") or record.get("qid") or "")
    qid = str(record.get("qid") or "")
    triples = []
    for triple in record.get("triples", []) if isinstance(record.get("triples"), list) else []:
        relation = str(triple.get("relation") or triple.get("predicate") or "")
        obj = str(triple.get("object") or "")
        triples.append(
            {
                **triple,
                "subject": title,
                "predicate": relation,
                "relation": relation,
                "object": obj,
                "qid": qid,
                "source_id": SOURCE_ID,
                "source": SOURCE_ID,
                "source_name": SOURCE_ID,
                "source_role": "primary",
                "source_url": url,
                "source_title": title,
                "schema_version": SCHEMA_VERSION,
                "validation_status": "accepted",
                "package_trial": True,
            }
        )
    return triples


def narratives_from_raw(record: Dict[str, Any], url: str) -> List[Dict[str, Any]]:
    title = str(record.get("title") or record.get("qid") or "")
    qid = str(record.get("qid") or "")
    rows = []
    for index, narrative in enumerate(record.get("narratives", []) if isinstance(record.get("narratives"), list) else []):
        rows.append(
            {
                **narrative,
                "page_title": title,
                "chunk_index": index,
                "source_id": SOURCE_ID,
                "source": SOURCE_ID,
                "source_name": SOURCE_ID,
                "source_role": "primary",
                "source_url": url,
                "source_title": title,
                "qid": qid,
                "schema_version": SCHEMA_VERSION,
                "package_trial": True,
            }
        )
    return rows


def normalize_existing_triples(rows: Sequence[Dict[str, Any]], url: str, qid: str) -> List[Dict[str, Any]]:
    output = []
    for row in rows:
        relation = str(row.get("predicate") or row.get("relation") or "")
        output.append(
            {
                **row,
                "predicate": relation,
                "relation": relation,
                "qid": qid,
                "source_id": SOURCE_ID,
                "source": SOURCE_ID,
                "source_name": SOURCE_ID,
                "source_role": "primary",
                "source_url": str(row.get("source_url") or url),
                "schema_version": row.get("schema_version") or SCHEMA_VERSION,
                "validation_status": "accepted",
                "package_trial": True,
            }
        )
    return output


def normalize_existing_narratives(rows: Sequence[Dict[str, Any]], url: str, qid: str) -> List[Dict[str, Any]]:
    output = []
    for row in rows:
        output.append(
            {
                **row,
                "qid": qid,
                "source_id": SOURCE_ID,
                "source": SOURCE_ID,
                "source_name": SOURCE_ID,
                "source_role": "primary",
                "source_url": str(row.get("source_url") or url),
                "schema_version": row.get("schema_version") or SCHEMA_VERSION,
                "package_trial": True,
            }
        )
    return output


def valid_item(item: Dict[str, Any]) -> bool:
    if item.get("source_id") != SOURCE_ID or not item.get("qid") or not item.get("title"):
        return False
    triples = item.get("triples", [])
    narratives = item.get("narratives", [])
    if not triples or not narratives:
        return False
    for triple in triples:
        if triple.get("source_id") != SOURCE_ID or triple.get("schema_version") != SCHEMA_VERSION or not triple.get("subject"):
            return False
    for narrative in narratives:
        if narrative.get("source_id") != SOURCE_ID or narrative.get("schema_version") != SCHEMA_VERSION:
            return False
    return True


def item_from_status(status: Dict[str, Any], triples_root: Path) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
    title = str(status.get("title") or status.get("qid") or "")
    qid = str(status.get("qid") or "")
    url = str(status.get("url") or f"https://www.wikidata.org/wiki/{qid}")
    raw_value = str(status.get("raw_path") or "")
    raw_path = Path(raw_value) if raw_value else Path()
    if raw_value and not raw_path.is_absolute():
        raw_path = ROOT / raw_path
    if raw_value and raw_path.exists():
        record = raw_record(raw_path)
        triples = triples_from_raw(record, url)
        narratives = narratives_from_raw(record, url)
    else:
        triples, narratives = materialized_pair(triples_root, title)
        triples = normalize_existing_triples(triples, url, qid)
        narratives = normalize_existing_narratives(narratives, url, qid)
    item = {"source_id": SOURCE_ID, "qid": qid, "title": title, "source_url": url, "raw_path": str(raw_path) if raw_path.exists() else "", "triples": triples, "narratives": narratives}
    if not valid_item(item):
        return None, {"status": "rejected", "reason": "missing_valid_triples_or_narratives", "qid": qid, "title": title, "url": url}
    return item, {"status": "packaged", "qid": qid, "title": title, "url": url}


def triple_key(row: Dict[str, Any]) -> tuple[str, str, str]:
    return (normalized_title(str(row.get("subject") or "")), str(row.get("predicate") or row.get("relation") or "").upper(), normalized_title(str(row.get("object") or "")))


def build_package_files(out_dir: Path, items: Sequence[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    triples: List[Dict[str, Any]] = []
    narratives: List[Dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        name = f"{index:02d}_{safe_name(str(item.get('title') or item.get('qid') or 'item'))}"
        triples.extend(item["triples"])
        narratives.extend(item["narratives"])
        write_json(out_dir / "triples_preview_by_item" / f"{name}.json", item["triples"])
        write_json(out_dir / "narratives_preview_by_item" / f"{name}.json", item["narratives"])
    write_json(out_dir / "triples_preview.json", triples)
    write_json(out_dir / "narratives_preview.json", narratives)
    return triples, narratives


def build_package(*, phase74_json: Path, triples_root: Path, out_dir: Path, approval_template: Path) -> Dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rejected_urls, rejected_titles = rejected_fingerprints(phase74_json)
    seen_urls: set[str] = set()
    seen_qids: set[str] = set()
    seen_titles: set[str] = set()
    seen_subjects: set[str] = set()
    seen_triples: set[tuple[str, str, str]] = set()
    packaged: List[Dict[str, Any]] = []
    statuses: List[Dict[str, Any]] = []
    duplicate_skipped = rejected_overlap_skipped = 0
    for status in accepted_statuses(phase74_json):
        item, item_status = item_from_status(status, triples_root)
        if not item:
            statuses.append(item_status)
            continue
        url_key = canonical_url(item["source_url"])
        qid_key = str(item["qid"])
        title_key = normalized_title(item["title"])
        subject_keys = {normalized_title(str(row.get("subject") or "")) for row in item["triples"]}
        subject_keys.discard("")
        item_triple_keys = {triple_key(row) for row in item["triples"]}
        if url_key in rejected_urls or title_key in rejected_titles:
            rejected_overlap_skipped += 1
            statuses.append({"status": "duplicate_skipped", "reason": "overlap_with_review_needed_or_rejected", "qid": qid_key, "title": item["title"], "url": item["source_url"]})
            continue
        if (
            (url_key and url_key in seen_urls)
            or (qid_key and qid_key in seen_qids)
            or (title_key and title_key in seen_titles)
            or (subject_keys & seen_subjects)
            or (item_triple_keys & seen_triples)
        ):
            duplicate_skipped += 1
            statuses.append({"status": "duplicate_skipped", "reason": "package_internal_url_qid_title_subject_overlap", "qid": qid_key, "title": item["title"], "url": item["source_url"]})
            continue
        seen_urls.add(url_key)
        seen_qids.add(qid_key)
        seen_titles.add(title_key)
        seen_subjects.update(subject_keys)
        seen_triples.update(item_triple_keys)
        packaged.append(item)
        statuses.append(item_status)
    triples, narratives = build_package_files(out_dir, packaged)
    samples = [{"title": item["title"], "qid": item["qid"], "url": item["source_url"], "triples": item["triples"][:4], "narratives": item["narratives"][:1], "warnings": []} for item in packaged[:5]]
    write_json(out_dir / "review_sample.json", samples)
    write_text(out_dir / "review_sample.md", "\n".join(f"- {row['title']} `{row['qid']}` triples={len(row['triples'])}" for row in samples) + "\n")
    write_json(approval_template, approval_payload(len(packaged)))
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {"package": "wikidata_shadow_package_phase75", "source_id": SOURCE_ID, "schema_version": SCHEMA_VERSION, "generated_at": generated_at, "items": len(packaged), "triples": len(triples), "narratives": len(narratives), "approval_status": "pending", "formal_write": False}
    write_json(out_dir / "package_manifest.json", manifest)
    relations = Counter(str(row.get("predicate") or row.get("relation") or "") for row in triples)
    return {
        "phase": "Phase 75",
        "mode": "wikidata_shadow_package_preparation",
        "generated_at": generated_at,
        "source_id": SOURCE_ID,
        "schema_version": SCHEMA_VERSION,
        "selected_count": len(accepted_statuses(phase74_json)),
        "packaged_items": len(packaged),
        "rejected": sum(1 for row in statuses if row.get("status") == "rejected"),
        "failed": sum(1 for row in statuses if row.get("status") == "failed"),
        "duplicate_skipped": duplicate_skipped,
        "rejected_overlap_skipped": rejected_overlap_skipped,
        "triples": len(triples),
        "narratives": len(narratives),
        "relations_count": dict(sorted(relations.items())),
        "candidate_statuses": statuses,
        "approval_status": "pending",
        "approval_template": str(approval_template),
        "out_dir": str(out_dir),
        "network_attempted": False,
        "formal_triples_write": False,
        "formal_narratives_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
    }


def render_md(report: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Wikidata shadow package preparation",
            "",
            f"- selected_count: `{report['selected_count']}`",
            f"- packaged_items: `{report['packaged_items']}`",
            f"- rejected: `{report['rejected']}`",
            f"- failed: `{report['failed']}`",
            f"- duplicate_skipped: `{report['duplicate_skipped']}`",
            f"- triples: `{report['triples']}`",
            f"- narratives: `{report['narratives']}`",
            f"- approval_status: `{report['approval_status']}`",
            f"- wikidata_registry: `{report['registry'].get('wikidata')}`",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build pending Wikidata shadow package from Phase74 accepted candidates.")
    parser.add_argument("--phase74-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "wikidata_controlled_assessment_phase74.json"))
    parser.add_argument("--triples-root", default=str(ROOT / "data" / "triples" / SOURCE_ID))
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "wikidata_shadow_package_phase75"))
    parser.add_argument("--report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "wikidata_shadow_package_phase75.json"))
    parser.add_argument("--report-md", default=str(ROOT / "docs" / "wikidata_shadow_package_phase75.md"))
    parser.add_argument("--approval-template", default=str(ROOT / "evaluation" / "four_source_expansion" / "wikidata_shadow_package_approval_phase75.json"))
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir)
    report_json = Path(args.report_json)
    report_md = Path(args.report_md)
    approval = Path(args.approval_template)
    if not output_allowed(out_dir) or not output_allowed(report_json) or not output_allowed(report_md, allow_docs=True) or not output_allowed(approval):
        print("outputs must stay under repo evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = build_package(phase74_json=Path(args.phase74_json), triples_root=Path(args.triples_root), out_dir=out_dir, approval_template=approval)
    write_json(report_json, report)
    write_text(report_md, render_md(report))
    print(f"packaged={report['packaged_items']} rejected={report['rejected']} skipped={report['duplicate_skipped'] + report['rejected_overlap_skipped']} failed={report['failed']} triples={report['triples']} narratives={report['narratives']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

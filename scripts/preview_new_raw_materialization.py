from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.materialize_manifest_raw_records import convert_raw_payload, raw_text_and_tables, raw_title, source_url
from scripts.preview_source_frontier import load_manifest, quality_context_from_manifest
from scripts.select_deduped_frontier_candidates import canonical_url, normalized_title
from src.source_quality.page_quality import score_page


ALLOWED_SOURCES = ("nasa", "esa")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def output_allowed(path: Path) -> bool:
    parts = list(path.resolve().parts)
    if "docs" in parts:
        return True
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1))


def written_items(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for source in report.get("sources", []) if isinstance(report.get("sources"), list) else []:
        source_id = str(source.get("source_id") or "").strip()
        if source_id not in ALLOWED_SOURCES:
            continue
        for item in source.get("items", []) if isinstance(source.get("items"), list) else []:
            if item.get("status") == "written":
                items.append({**item, "source_id": source_id})
    return items


def raw_files(raw_root: Path, source_id: str) -> List[Path]:
    path = raw_root / source_id
    return sorted(path.glob("*.json")) if path.exists() else []


def find_raw_path(item: Dict[str, Any], raw_root: Path) -> Path | None:
    saved = Path(str(item.get("saved_path") or ""))
    if saved.exists():
        return saved
    source_id = str(item.get("source_id") or "")
    wanted_url = canonical_url(str(item.get("url") or ""))
    wanted_title = normalized_title(str(item.get("title") or ""))
    for path in raw_files(raw_root, source_id):
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        if wanted_url and canonical_url(source_url(payload)) == wanted_url:
            return path
        if wanted_title and normalized_title(raw_title(source_id, payload)) == wanted_title:
            return path
    return None


def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16] if text else ""


def duplicate_key(entry: Dict[str, Any]) -> str:
    if entry.get("canonical_url"):
        return f"url:{entry['canonical_url']}"
    if entry.get("normalized_title"):
        return f"title:{entry['normalized_title']}"
    if entry.get("text_hash"):
        return f"text:{entry['text_hash']}"
    return ""


def quality_context(source_id: str) -> Dict[str, Any]:
    try:
        return quality_context_from_manifest(load_manifest(source_id))
    except Exception:
        return {}


def preview_item(item: Dict[str, Any], raw_root: Path) -> Dict[str, Any]:
    source_id = str(item.get("source_id") or "")
    path = find_raw_path(item, raw_root)
    if not path:
        return {
            "source_id": source_id,
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "status": "missing_raw",
            "warning": "raw file not found",
            "candidate_triples_preview_count": 0,
            "candidate_narratives_preview_count": 0,
        }
    payload = read_json(path)
    if not isinstance(payload, dict):
        return {
            "source_id": source_id,
            "raw_path": str(path),
            "status": "unreadable_raw",
            "warning": "raw JSON is not an object",
            "candidate_triples_preview_count": 0,
            "candidate_narratives_preview_count": 0,
        }
    text, rows = raw_text_and_tables(payload)
    title = raw_title(source_id, payload)
    url = source_url(payload)
    quality = score_page(
        {"title": title, "url": url, "text": text, "html": payload.get("html", ""), "source_name": source_id},
        quality_context=quality_context(source_id),
    )
    converted = convert_raw_payload(source_id, payload)
    risks: List[str] = []
    if len(text) < 80:
        risks.append("short_text")
    if quality["triage"] == "rejected":
        risks.append("quality_rejected")
    if not converted.get("triples") and not converted.get("narratives"):
        risks.append("no_materialization_candidates")
    return {
        "source_id": source_id,
        "raw_path": str(path),
        "url": url,
        "title": title,
        "status": "readable",
        "text_length": len(text),
        "table_count": len(rows),
        "canonical_url": canonical_url(url),
        "normalized_title": normalized_title(title),
        "text_hash": text_hash(text),
        "quality_score": quality["score"],
        "quality_triage": quality["triage"],
        "quality_reasons": quality["reasons"],
        "candidate_triples_preview_count": len(converted.get("triples", [])),
        "candidate_narratives_preview_count": len(converted.get("narratives", [])),
        "extraction_risks": risks,
    }


def mark_duplicate_groups(items: List[Dict[str, Any]]) -> int:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in items:
        key = duplicate_key(item)
        if key:
            groups[key].append(item)
    duplicate_count = 0
    group_index = 1
    for group_items in groups.values():
        if len(group_items) < 2:
            continue
        group_id = f"dup_{group_index}"
        group_index += 1
        duplicate_count += 1
        for item in group_items:
            item["duplicate_group"] = group_id
            item.setdefault("extraction_risks", []).append("duplicate_candidate")
    return duplicate_count


def source_summaries(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summaries = []
    for source_id in ALLOWED_SOURCES:
        source_items = [item for item in items if item.get("source_id") == source_id]
        if not source_items:
            continue
        triage = Counter(str(item.get("quality_triage") or "missing") for item in source_items)
        readable = [item for item in source_items if item.get("status") == "readable"]
        rejected = triage.get("rejected", 0)
        reviewish = triage.get("accepted", 0) + triage.get("review_needed", 0)
        if any(item.get("duplicate_group") for item in readable):
            action = "dedupe_before_materialization"
        elif readable and reviewish >= max(1, len(readable) // 2) and rejected <= len(readable) // 3:
            action = "ready_for_limited_shadow_triples_trial"
        else:
            action = "manual_review_before_materialization"
        summaries.append({
            "source_id": source_id,
            "new_raw_count": len(source_items),
            "readable_count": len(readable),
            "triage_counts": dict(sorted(triage.items())),
            "preview_triples_total": sum(int(item.get("candidate_triples_preview_count", 0)) for item in source_items),
            "preview_narratives_total": sum(int(item.get("candidate_narratives_preview_count", 0)) for item in source_items),
            "recommended_next_action": action,
        })
    return summaries


def build_report(*, ingest_report: Path, root: Path = ROOT) -> Dict[str, Any]:
    raw_root = root / "data" / "raw_json"
    phase41 = read_json(ingest_report)
    items = [preview_item(item, raw_root) for item in written_items(phase41 if isinstance(phase41, dict) else {})]
    duplicate_groups = mark_duplicate_groups(items)
    triage = Counter(str(item.get("quality_triage") or "missing") for item in items)
    readable = [item for item in items if item.get("status") == "readable"]
    missing = [item for item in items if item.get("status") != "readable"]
    summaries = source_summaries(items)
    overall_actions = {item["recommended_next_action"] for item in summaries}
    if "dedupe_before_materialization" in overall_actions:
        action = "dedupe_before_materialization"
    elif summaries and all(item["recommended_next_action"] == "ready_for_limited_shadow_triples_trial" for item in summaries):
        action = "ready_for_limited_shadow_triples_trial"
    else:
        action = "manual_review_before_materialization"
    return {
        "phase": "Phase 42",
        "mode": "new_raw_materialization_preview",
        "generated_at": utc_now(),
        "ingest_report": str(ingest_report),
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "summary": {
            "new_raw_count": len(items),
            "readable_count": len(readable),
            "missing_raw_count": len(missing),
            "triage_counts": dict(sorted(triage.items())),
            "duplicate_groups": duplicate_groups,
            "preview_triples_total": sum(int(item.get("candidate_triples_preview_count", 0)) for item in items),
            "preview_narratives_total": sum(int(item.get("candidate_narratives_preview_count", 0)) for item in items),
            "recommended_next_action": action,
        },
        "sources": summaries,
        "items": items,
        "safety_flags": {
            "network": False,
            "triples_write": False,
            "narratives_write": False,
            "chroma_write": False,
            "neo4j_write": False,
            "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        },
    }


def render_markdown(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 新增 raw materialization preview",
        "",
        "本报告只读取 Phase 41 新增 raw，做质量抽样与内存估算，不写 triples/narratives/Chroma/Neo4j。",
        "",
        f"- phase: `{report['phase']}`",
        f"- active_source: `{report['active_source']}`",
        f"- new raw: `{summary['new_raw_count']}`",
        f"- readable: `{summary['readable_count']}`",
        f"- duplicate groups: `{summary['duplicate_groups']}`",
        f"- preview triples: `{summary['preview_triples_total']}`",
        f"- preview narratives: `{summary['preview_narratives_total']}`",
        f"- recommended next action: `{summary['recommended_next_action']}`",
        "",
        "| source | new raw | readable | triage | preview triples | preview narratives | next action |",
        "|---|---:|---:|---|---:|---:|---|",
    ]
    for item in report["sources"]:
        lines.append(
            f"| {item['source_id']} | {item['new_raw_count']} | {item['readable_count']} | "
            f"`{item['triage_counts']}` | {item['preview_triples_total']} | {item['preview_narratives_total']} | "
            f"`{item['recommended_next_action']}` |"
        )
    lines.extend(["", "## Sample Items", ""])
    for item in report["items"][:25]:
        lines.append(
            f"- `{item.get('source_id')}` `{item.get('quality_triage', item.get('status'))}` "
            f"triples={item.get('candidate_triples_preview_count', 0)} "
            f"narratives={item.get('candidate_narratives_preview_count', 0)} "
            f"{item.get('title') or item.get('url')}"
        )
    lines.extend(["", "## Safety", ""])
    for key, value in report["safety_flags"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Preview Phase 41 new raw materialization without downstream writes.")
    parser.add_argument("--ingest-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "selected_raw_shadow_ingest_phase41.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "new_raw_materialization_preview_phase42.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "new_raw_materialization_preview_phase42.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = build_report(ingest_report=Path(args.ingest_report))
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    print(
        f"new_raw={report['summary']['new_raw_count']} readable={report['summary']['readable_count']} "
        f"triage={report['summary']['triage_counts']} triples_preview={report['summary']['preview_triples_total']} "
        f"narratives_preview={report['summary']['preview_narratives_total']} action={report['summary']['recommended_next_action']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.build_nasa_limited_shadow_package import formal_shadow_plan, render_review_sample
from scripts.ingest_manifest_frontier import quality_fields_for_payload
from scripts.materialize_manifest_raw_records import clean_text, convert_raw_payload, safe_name
from scripts.select_deduped_frontier_candidates import canonical_url, normalized_title


SOURCE_ID = "esa"


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


def approval_payload(item_count: int) -> Dict[str, Any]:
    return {
        "source_id": SOURCE_ID,
        "approval_decision": "pending",
        "approved_item_count": 0,
        "max_available_item_count": item_count,
        "reviewer_notes": "",
        "allowed_output_scope": "data/triples_shadow/esa only after explicit guarded approval",
    }


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return relative.parts[:2] == ("evaluation", "four_source_expansion") or (allow_docs and relative.parts[:1] == ("docs",))


def esa_url_allowed(url: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return host == "esa.int" or host.endswith(".esa.int")


def normalize_esa_title(title: str) -> str:
    title = re.sub(r"^ESA\s*-\s*", "", clean_text(title))
    return title or "ESA item"


def accepted_statuses(*paths: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in paths:
        report = read_json(path)
        for row in report.get("candidate_statuses", []) if isinstance(report, dict) else []:
            if row.get("status") == "accepted_for_package":
                rows.append(row)
    return rows


def rejected_failed_fingerprints(*paths: Path) -> tuple[set[str], set[str]]:
    urls: set[str] = set()
    titles: set[str] = set()
    for path in paths:
        report = read_json(path)
        for row in report.get("candidate_statuses", []) if isinstance(report, dict) else []:
            if row.get("status") not in {"rejected", "failed"}:
                continue
            url = canonical_url(str(row.get("url") or ""))
            title = normalized_title(str(row.get("title") or ""))
            if url:
                urls.add(url)
            if title:
                titles.add(title)
    return urls, titles


def raw_path_for_status(status: Dict[str, Any]) -> Path:
    raw_path = status.get("raw_preview_path") or status.get("raw_path") or ""
    return (ROOT / raw_path).resolve() if raw_path and not Path(str(raw_path)).is_absolute() else Path(str(raw_path))


def topic_for(title: str, text: str) -> str:
    haystack = f"{title} {text[:1600]}".lower()
    for topic, needles in {
        "space science mission": ("mission", "spacecraft", "orbiter", "telescope", "probe"),
        "exoplanet science": ("exoplanet", "planet outside", "plato", "cheops"),
        "cosmology": ("universe", "galaxy", "quasar", "cosmic"),
        "solar system science": ("solar system", "mars", "mercury", "comet", "asteroid"),
    }.items():
        if any(needle in haystack for needle in needles):
            return topic
    return "space science"


def make_triple(subject: str, predicate: str, obj: str, evidence: str, confidence: float) -> Dict[str, Any]:
    return {
        "subject": clean_text(subject),
        "predicate": predicate,
        "object": clean_text(obj),
        "evidence": clean_text(evidence)[:280],
        "confidence": round(confidence, 2),
        "validation_status": "accepted",
    }


def triples_for(raw: Dict[str, Any], narratives: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    title = normalize_esa_title(str(raw.get("title") or "ESA item"))
    url = str(raw.get("source_url") or raw.get("url") or "")
    text = clean_text(raw.get("text") or " ".join(str(n.get("content") or "") for n in narratives if isinstance(n, dict)))
    topic = topic_for(title, text)
    evidence = text[:280] or title
    triples = [
        make_triple(title, "SOURCE_URL", url, url, 0.99),
        make_triple(title, "HAS_TOPIC", topic, evidence, 0.84),
        make_triple(title, "INSTANCE_OF", "ESA space science page", evidence, 0.82),
    ]
    if any(word in f"{title} {text[:1200]}".lower() for word in ("mission", "spacecraft", "orbiter", "telescope", "probe")):
        triples.append(make_triple(title, "INSTANCE_OF", "space mission page", evidence, 0.74))
    return triples


def item_from_status(status: Dict[str, Any]) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
    raw_path = raw_path_for_status(status)
    raw = read_json(raw_path)
    if not isinstance(raw, dict) or not raw:
        return None, {"status": "failed", "reason": "raw_preview_missing", "url": status.get("url", ""), "title": status.get("title", "")}
    raw.update(quality_fields_for_payload(raw))
    title = normalize_esa_title(str(raw.get("title") or status.get("title") or "ESA item"))
    url = str(raw.get("source_url") or raw.get("url") or status.get("url") or "")
    if raw.get("quality_triage") != "accepted":
        return None, {"status": "rejected", "reason": f"quality_{raw.get('quality_triage')}", "title": title, "url": url}
    converted = convert_raw_payload(SOURCE_ID, raw)
    narratives = converted.get("narratives", []) if isinstance(converted.get("narratives"), list) else []
    triples = triples_for(raw, narratives)
    if not narratives or not triples or not esa_url_allowed(url):
        return None, {"status": "rejected", "reason": "missing_narratives_triples_or_allowed_url", "title": title, "url": url}
    return {
        "source_id": SOURCE_ID,
        "title": title,
        "source_url": url,
        "raw_preview_path": str(raw_path),
        "triples": triples,
        "narratives": narratives,
    }, {"status": "packaged", "title": title, "url": url}


def build_package_files(out_dir: Path, items: Sequence[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    triples: List[Dict[str, Any]] = []
    narratives: List[Dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        name = f"{index:02d}_{safe_name(str(item.get('title') or 'item'))}"
        item_triples = [{**triple, "source_id": SOURCE_ID, "source_url": item["source_url"], "source_title": item["title"], "package_trial": True} for triple in item["triples"]]
        item_narratives = [{**narrative, "source_id": SOURCE_ID, "source_url": item["source_url"], "source_title": item["title"], "package_trial": True} for narrative in item["narratives"]]
        triples.extend(item_triples)
        narratives.extend(item_narratives)
        write_json(out_dir / "triples_preview_by_item" / f"{name}.json", item_triples)
        write_json(out_dir / "narratives_preview_by_item" / f"{name}.json", item_narratives)
    write_json(out_dir / "triples_preview.json", triples)
    write_json(out_dir / "narratives_preview.json", narratives)
    return triples, narratives


def build_esa_package(*, phase67_json: Path, phase68_json: Path, out_dir: Path, approval_template: Path) -> Dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rejected_urls, rejected_titles = rejected_failed_fingerprints(phase67_json, phase68_json)
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    seen_subjects: set[str] = set()
    packaged: List[Dict[str, Any]] = []
    statuses: List[Dict[str, Any]] = []
    duplicate_skipped = rejected_failed_skipped = 0
    for status in accepted_statuses(phase67_json, phase68_json):
        item, item_status = item_from_status(status)
        if item:
            url_key = canonical_url(item["source_url"])
            title_key = normalized_title(item["title"])
            subject_keys = {normalized_title(str(t.get("subject") or "")) for t in item["triples"]}
            subject_keys.discard("")
            if url_key in rejected_urls or title_key in rejected_titles:
                rejected_failed_skipped += 1
                statuses.append({"status": "duplicate_skipped", "reason": "overlap_with_rejected_or_failed", "title": item["title"], "url": item["source_url"]})
                continue
            if (url_key and url_key in seen_urls) or (title_key and title_key in seen_titles) or (subject_keys & seen_subjects):
                duplicate_skipped += 1
                statuses.append({"status": "duplicate_skipped", "reason": "package_internal_url_title_subject_overlap", "title": item["title"], "url": item["source_url"]})
                continue
            seen_urls.add(url_key)
            seen_titles.add(title_key)
            seen_subjects.update(subject_keys)
            packaged.append(item)
        statuses.append(item_status)
    triples, narratives = build_package_files(out_dir, packaged)
    samples = [
        {"title": i["title"], "url": i["source_url"], "triples": i["triples"][:4], "narratives": i["narratives"][:1], "warnings": []}
        for i in packaged[:5]
    ]
    write_json(out_dir / "review_sample.json", samples)
    write_text(out_dir / "review_sample.md", render_review_sample(samples))
    write_json(approval_template, approval_payload(len(packaged)))
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {"package": "esa_shadow_package_phase69", "source_id": SOURCE_ID, "generated_at": generated_at, "items": len(packaged), "triples": len(triples), "narratives": len(narratives), "approval_status": "pending", "formal_write": False}
    write_json(out_dir / "package_manifest.json", manifest)
    relation_counts = Counter(triple.get("predicate", "") for triple in triples)
    return {
        "phase": "Phase 69",
        "mode": "esa_shadow_package_preparation",
        "generated_at": generated_at,
        "source_id": SOURCE_ID,
        "selected_count": len(accepted_statuses(phase67_json, phase68_json)),
        "packaged_items": len(packaged),
        "rejected": sum(1 for row in statuses if row.get("status") == "rejected"),
        "failed": sum(1 for row in statuses if row.get("status") == "failed"),
        "duplicate_skipped": duplicate_skipped,
        "rejected_failed_skipped": rejected_failed_skipped,
        "triples": len(triples),
        "narratives": len(narratives),
        "relations_count": dict(sorted(relation_counts.items())),
        "candidate_statuses": statuses,
        "approval_status": "pending",
        "approval_template": str(approval_template),
        "out_dir": str(out_dir),
        "formal_shadow_write_plan": formal_shadow_plan(len(packaged), len(triples), len(narratives)),
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
            "# ESA shadow package preparation",
            "",
            f"- selected_count: `{report['selected_count']}`",
            f"- packaged_items: `{report['packaged_items']}`",
            f"- rejected: `{report['rejected']}`",
            f"- failed: `{report['failed']}`",
            f"- duplicate_skipped: `{report['duplicate_skipped']}`",
            f"- rejected_failed_skipped: `{report['rejected_failed_skipped']}`",
            f"- triples: `{report['triples']}`",
            f"- narratives: `{report['narratives']}`",
            f"- approval_status: `{report['approval_status']}`",
            f"- chroma_write: `{report['chroma_write']}`",
            f"- neo4j_write: `{report['neo4j_write']}`",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build ESA pending shadow package from Phase67 and Phase68 accepted preview items.")
    parser.add_argument("--phase67-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_controlled_assessment_phase67.json"))
    parser.add_argument("--phase68-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_raw_preview_batch_phase68.json"))
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_shadow_package_phase69"))
    parser.add_argument("--report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_shadow_package_phase69.json"))
    parser.add_argument("--report-md", default=str(ROOT / "docs" / "esa_shadow_package_phase69.md"))
    parser.add_argument("--approval-template", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_shadow_package_approval_phase69.json"))
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir)
    report_json = Path(args.report_json)
    report_md = Path(args.report_md)
    approval = Path(args.approval_template)
    if not output_allowed(out_dir) or not output_allowed(report_json) or not output_allowed(report_md, allow_docs=True) or not output_allowed(approval):
        print("outputs must stay under repo evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = build_esa_package(phase67_json=Path(args.phase67_json), phase68_json=Path(args.phase68_json), out_dir=out_dir, approval_template=approval)
    write_json(report_json, report)
    write_text(report_md, render_md(report))
    print(f"packaged={report['packaged_items']} rejected={report['rejected']} skipped={report['duplicate_skipped'] + report['rejected_failed_skipped']} failed={report['failed']} triples={report['triples']} narratives={report['narratives']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

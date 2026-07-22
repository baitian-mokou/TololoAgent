from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.materialize_manifest_raw_records import clean_text, safe_name


SOURCE_ID = "nasa"
MIN_CONFIDENCE = 0.65


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


def under_four_source_expansion(path: Path) -> bool:
    parts = list(path.resolve().parts)
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1))


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    parts = list(path.resolve().parts)
    if allow_docs and "docs" in parts:
        return True
    return under_four_source_expansion(path)


def item_key(title: str, url: str) -> str:
    url_key = clean_text(url).lower().rstrip("/")
    if url_key:
        return f"url:{url_key}"
    return f"title:{clean_text(title).lower()}"


def nasa_url_allowed(url: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return host == "nasa.gov" or host.endswith(".nasa.gov")


def load_narrative_items(directory: Path) -> Dict[str, Dict[str, Any]]:
    items: Dict[str, Dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        payload = read_json(path)
        if not isinstance(payload, dict) or payload.get("source_id") != SOURCE_ID:
            continue
        title = clean_text(payload.get("title") or "")
        url = clean_text(payload.get("source_url") or payload.get("url") or "")
        narratives = payload.get("narratives", []) if isinstance(payload.get("narratives"), list) else []
        key = item_key(title, url)
        items[key] = {
            "title": title,
            "source_url": url,
            "narratives": narratives,
            "narrative_path": str(path),
            "raw_path": payload.get("raw_path", ""),
        }
    return items


def load_relation_items(directory: Path) -> Dict[str, Dict[str, Any]]:
    items: Dict[str, Dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        payload = read_json(path)
        if not isinstance(payload, dict) or payload.get("source_id") != SOURCE_ID:
            continue
        title = clean_text(payload.get("title") or "")
        url = clean_text(payload.get("url") or payload.get("source_url") or "")
        triples = payload.get("triples_preview", []) if isinstance(payload.get("triples_preview"), list) else []
        key = item_key(title, url)
        items[key] = {
            "title": title,
            "source_url": url,
            "triples": triples,
            "relation_path": str(path),
            "raw_path": payload.get("raw_path", ""),
        }
    return items


def triple_key(triple: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        clean_text(triple.get("subject", "")).lower(),
        clean_text(triple.get("predicate", "")).upper(),
        clean_text(triple.get("object", "")).lower(),
    )


def validate_and_dedupe_triples(triples: Sequence[Dict[str, Any]], url: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    accepted: List[Dict[str, Any]] = []
    flags: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str]] = set()
    url_ok = nasa_url_allowed(url)
    for triple in triples:
        reason = ""
        key = triple_key(triple)
        if not all(clean_text(triple.get(field, "")) for field in ("subject", "predicate", "object")):
            reason = "triple_empty_field"
        elif not clean_text(triple.get("evidence", "")):
            reason = "triple_missing_evidence"
        elif float(triple.get("confidence", 0) or 0) < MIN_CONFIDENCE:
            reason = "triple_low_confidence"
        elif not url_ok:
            reason = "source_url_not_allowed"
        elif key in seen:
            reason = "duplicate_triple"
        if reason:
            flags.append({"reason": reason, "triple": triple})
            continue
        seen.add(key)
        accepted.append({**triple, "source_url": url, "source_id": SOURCE_ID, "package_trial": True})
    return accepted, flags


def merge_items(narratives: Dict[str, Dict[str, Any]], relations: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    merged: List[Dict[str, Any]] = []
    flags: List[Dict[str, Any]] = []
    for key in sorted(set(narratives) | set(relations)):
        narrative = narratives.get(key, {})
        relation = relations.get(key, {})
        title = clean_text(relation.get("title") or narrative.get("title") or key)
        url = clean_text(relation.get("source_url") or narrative.get("source_url") or "")
        item_narratives = narrative.get("narratives", []) if isinstance(narrative.get("narratives"), list) else []
        accepted_triples, triple_flags = validate_and_dedupe_triples(relation.get("triples", []), url)
        for flag in triple_flags:
            flags.append({"title": title, "url": url, **flag})
        if not item_narratives:
            flags.append({"title": title, "url": url, "reason": "missing_narrative"})
        if not accepted_triples:
            flags.append({"title": title, "url": url, "reason": "missing_accepted_triple"})
        if not url:
            flags.append({"title": title, "url": url, "reason": "missing_source_url"})
        merged.append({
            "source_id": SOURCE_ID,
            "title": title,
            "source_url": url,
            "raw_path": relation.get("raw_path") or narrative.get("raw_path", ""),
            "triples": accepted_triples,
            "narratives": item_narratives,
            "narrative_path": narrative.get("narrative_path", ""),
            "relation_path": relation.get("relation_path", ""),
            "warnings": [flag for flag in flags if flag.get("title") == title and flag.get("url") == url],
        })
    return merged, flags


def flatten(items: Sequence[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in items:
        for record in item.get(field, []) if isinstance(item.get(field), list) else []:
            enriched = dict(record)
            enriched.setdefault("source_id", SOURCE_ID)
            enriched.setdefault("source_url", item.get("source_url", ""))
            enriched.setdefault("source_title", item.get("title", ""))
            enriched.setdefault("package_trial", True)
            result.append(enriched)
    return result


def write_package_files(out_dir: Path, items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    triples_dir = out_dir / "triples_preview_by_item"
    narratives_dir = out_dir / "narratives_preview_by_item"
    triples = flatten(items, "triples")
    narratives = flatten(items, "narratives")
    write_json(out_dir / "triples_preview.json", triples)
    write_json(out_dir / "narratives_preview.json", narratives)
    item_paths = []
    for item in items:
        name = safe_name(str(item.get("title") or "item"))
        triple_path = triples_dir / f"{name}.json"
        narrative_path = narratives_dir / f"{name}.json"
        write_json(triple_path, item.get("triples", []))
        write_json(narrative_path, item.get("narratives", []))
        item_paths.append({"title": item.get("title", ""), "triples_path": str(triple_path), "narratives_path": str(narrative_path)})
    return {"triples": triples, "narratives": narratives, "item_paths": item_paths}


def sample_items(items: Sequence[Dict[str, Any]], count: int = 5) -> List[Dict[str, Any]]:
    samples = []
    for item in list(items)[:count]:
        samples.append({
            "title": item.get("title", ""),
            "url": item.get("source_url", ""),
            "triples": item.get("triples", [])[:4],
            "narratives": item.get("narratives", [])[:1],
            "warnings": item.get("warnings", []),
        })
    return samples


def render_review_sample(samples: Sequence[Dict[str, Any]]) -> str:
    lines = ["# NASA limited shadow package review sample", ""]
    for sample in samples:
        lines.extend([f"## {sample['title']}", "", f"- url: `{sample['url']}`", ""])
        lines.append("Triples:")
        for triple in sample["triples"]:
            lines.append(f"- `{triple.get('subject')}` `{triple.get('predicate')}` `{triple.get('object')}` evidence: {triple.get('evidence')}")
        lines.append("")
        lines.append("Narrative sample:")
        for narrative in sample["narratives"]:
            lines.append(f"- {clean_text(narrative.get('content', ''))[:320]}")
        if sample["warnings"]:
            lines.append("")
            lines.append(f"Warnings: `{[warning.get('reason') for warning in sample['warnings']]}`")
        lines.append("")
    return "\n".join(lines)


def approval_payload(item_count: int) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "source_id": SOURCE_ID,
        "approval_decision": "pending",
        "approved_item_count": 0,
        "max_available_item_count": item_count,
        "reviewer_notes": "",
        "allowed_output_scope": "formal shadow triples directory only after explicit approval; no active source change; no Chroma or Neo4j write",
    }


def formal_shadow_plan(item_count: int, triples: int, narratives: int) -> Dict[str, Any]:
    return {
        "execution_status": "not_run",
        "requires_manual_approval": True,
        "source_id": SOURCE_ID,
        "approved_item_count_required": item_count,
        "planned_triples": triples,
        "planned_narratives": narratives,
        "allowed_scope": "shadow materialization path only",
        "safety_guards": [
            "ACTIVE_SOURCE remains zh_wikipedia",
            "nasa remains disabled/shadow",
            "no Chroma write",
            "no Neo4j write",
            "manual approval file required before any formal shadow write",
        ],
    }


def build_package(
    *,
    narrative_trial_json: Path,
    narrative_trial_dir: Path,
    relation_preview_json: Path,
    relation_preview_dir: Path,
    out_dir: Path,
    approval_template: Path,
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    narratives = load_narrative_items(narrative_trial_dir)
    relations = load_relation_items(relation_preview_dir)
    items, flags = merge_items(narratives, relations)
    package_files = write_package_files(out_dir, items)
    samples = sample_items(items)
    write_json(out_dir / "review_sample.json", samples)
    write_text(out_dir / "review_sample.md", render_review_sample(samples))

    relation_counts = Counter(triple.get("predicate", "") for triple in package_files["triples"])
    type_distribution = Counter(
        triple.get("object", "")
        for triple in package_files["triples"]
        if triple.get("predicate") in {"INSTANCE_OF", "HAS_TOPIC"}
    )
    approval = approval_payload(len(items))
    write_json(approval_template, approval)
    manifest = {
        "package": "nasa_limited_shadow_package_phase45",
        "source_id": SOURCE_ID,
        "generated_at": utc_now(),
        "items": len(items),
        "triples": len(package_files["triples"]),
        "narratives": len(package_files["narratives"]),
        "narrative_trial_json": str(narrative_trial_json),
        "relation_preview_json": str(relation_preview_json),
        "formal_write": False,
        "approval_status": approval["approval_decision"],
        "files": {
            "triples_preview": str(out_dir / "triples_preview.json"),
            "narratives_preview": str(out_dir / "narratives_preview.json"),
            "review_sample": str(out_dir / "review_sample.md"),
        },
    }
    write_json(out_dir / "package_manifest.json", manifest)
    action = (
        "ready_for_manual_approval_to_write_formal_shadow_directory"
        if items and len(package_files["triples"]) and len(package_files["narratives"]) and not flags
        else "review_quality_flags_before_shadow_write"
    )
    return {
        "phase": "Phase 45",
        "mode": "nasa_limited_shadow_materialization_package",
        "generated_at": manifest["generated_at"],
        "source_id": SOURCE_ID,
        "items": len(items),
        "triples": len(package_files["triples"]),
        "narratives": len(package_files["narratives"]),
        "relations_count": dict(sorted(relation_counts.items())),
        "type_distribution": dict(sorted(type_distribution.items())),
        "sample_items": samples,
        "quality_flags": flags,
        "approval_status": approval["approval_decision"],
        "approval_template": str(approval_template),
        "out_dir": str(out_dir),
        "formal_shadow_write_plan": formal_shadow_plan(len(items), len(package_files["triples"]), len(package_files["narratives"])),
        "formal_triples_write": False,
        "formal_narratives_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "network": False,
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "recommended_next_action": action,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# NASA limited shadow materialization package",
        "",
        "本包合并 Phase 43 narratives 与 Phase 44 accepted triples，仅用于人工审阅和下一步审批；当前不写正式 shadow 目录。",
        "",
        f"- source: `{report['source_id']}`",
        f"- items: `{report['items']}`",
        f"- triples: `{report['triples']}`",
        f"- narratives: `{report['narratives']}`",
        f"- approval_status: `{report['approval_status']}`",
        f"- quality_flags: `{len(report['quality_flags'])}`",
        f"- next_action: `{report['recommended_next_action']}`",
        "",
        "## Relation Counts",
        "",
    ]
    for relation, count in report["relations_count"].items():
        lines.append(f"- `{relation}`: {count}")
    lines.extend(["", "## Type Distribution", ""])
    for value, count in report["type_distribution"].items():
        lines.append(f"- `{value}`: {count}")
    lines.extend(["", "## Approval Template", "", f"- `{report['approval_template']}`", "", "## Formal Shadow Write Plan", ""])
    plan = report["formal_shadow_write_plan"]
    lines.extend([
        f"- execution_status: `{plan['execution_status']}`",
        f"- requires_manual_approval: `{plan['requires_manual_approval']}`",
        f"- allowed_scope: `{plan['allowed_scope']}`",
        f"- planned_triples: `{plan['planned_triples']}`",
        f"- planned_narratives: `{plan['planned_narratives']}`",
        "",
        "Safety guards:",
    ])
    for guard in plan["safety_guards"]:
        lines.append(f"- {guard}")
    lines.extend(["", "## Review Samples", ""])
    for sample in report["sample_items"]:
        lines.append(f"- {sample['title']} - `{sample['url']}` triples={len(sample['triples'])} narratives={len(sample['narratives'])}")
    lines.extend(["", "## Safety", ""])
    for key in ("formal_triples_write", "formal_narratives_write", "chroma_write", "neo4j_write", "network", "active_source_unchanged"):
        lines.append(f"- {key}: `{report[key]}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build NASA limited shadow materialization package in evaluation only.")
    parser.add_argument("--narrative-trial-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_triples_trial_phase43.json"))
    parser.add_argument("--narrative-trial-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_triples_trial_phase43"))
    parser.add_argument("--relation-preview-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_text_relation_preview_phase44.json"))
    parser.add_argument("--relation-preview-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_text_relation_preview_phase44"))
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_limited_shadow_package_phase45"))
    parser.add_argument("--report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_limited_shadow_package_phase45.json"))
    parser.add_argument("--report-md", default=str(ROOT / "docs" / "nasa_limited_shadow_package_phase45.md"))
    parser.add_argument("--approval-template", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_limited_shadow_package_approval_phase45.json"))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    report_json = Path(args.report_json)
    report_md = Path(args.report_md)
    approval = Path(args.approval_template)
    if not output_allowed(out_dir) or not output_allowed(report_json) or not output_allowed(report_md, allow_docs=True) or not output_allowed(approval):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = build_package(
        narrative_trial_json=Path(args.narrative_trial_json),
        narrative_trial_dir=Path(args.narrative_trial_dir),
        relation_preview_json=Path(args.relation_preview_json),
        relation_preview_dir=Path(args.relation_preview_dir),
        out_dir=out_dir,
        approval_template=approval,
    )
    write_json(report_json, report)
    write_text(report_md, render_markdown(report))
    print(
        f"source={report['source_id']} items={report['items']} triples={report['triples']} "
        f"narratives={report['narratives']} flags={len(report['quality_flags'])} "
        f"approval={report['approval_status']} action={report['recommended_next_action']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

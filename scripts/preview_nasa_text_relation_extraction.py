from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
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


def normalize_title(title: str) -> str:
    title = re.sub(r"\s*-\s*NASA.*$", "", clean_text(title))
    return title or "NASA item"


def nasa_url_allowed(url: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return host == "nasa.gov" or host.endswith(".nasa.gov")


def phase42_accepted_raw_paths(path: Path) -> set[str]:
    payload = read_json(path)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return {
        str(item.get("raw_path") or "")
        for item in items
        if item.get("source_id") == SOURCE_ID and item.get("quality_triage") == "accepted" and item.get("raw_path")
    }


def trial_items(trial_dir: Path, accepted_raw_paths: set[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for path in sorted(trial_dir.glob("*.json")) if trial_dir.exists() else []:
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        if payload.get("source_id") != SOURCE_ID:
            continue
        if str(payload.get("raw_path") or "") not in accepted_raw_paths:
            continue
        payload["_trial_path"] = str(path)
        items.append(payload)
    return items


def narrative_text(item: Dict[str, Any]) -> Tuple[str, int]:
    narratives = item.get("narratives", []) if isinstance(item.get("narratives"), list) else []
    chunks = [clean_text(narrative.get("content", "")) for narrative in narratives if isinstance(narrative, dict)]
    return clean_text(" ".join(chunk for chunk in chunks if chunk)), len(chunks)


def sentence_with(text: str, pattern: str, fallback: str = "") -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(pattern, sentence, flags=re.I):
            return clean_text(sentence)[:280]
    return clean_text(fallback or text)[:280]


def make_triple(subject: str, predicate: str, obj: str, evidence: str, confidence: float) -> Dict[str, Any]:
    return {
        "subject": clean_text(subject),
        "predicate": clean_text(predicate).upper(),
        "object": clean_text(obj),
        "evidence": clean_text(evidence),
        "confidence": round(float(confidence), 2),
    }


def object_type(title: str, url: str, text: str) -> str:
    title_url = f"{title} {url}".lower()
    if "asteroid" in title_url or "near-earth object" in title_url:
        return "asteroid"
    if "comet" in title_url:
        return "comet"
    if "meteor" in title_url:
        return "small body"
    body = text[:2000].lower()
    if "near-earth asteroid" in body or " asteroid" in body:
        return "asteroid"
    if " comet" in body:
        return "comet"
    if " meteor" in body:
        return "small body"
    return "solar system object"


def extract_text_relations(item: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
    title = normalize_title(str(item.get("title") or ""))
    url = str(item.get("source_url") or item.get("url") or "")
    text, narrative_count = narrative_text(item)
    haystack = f"{title}. {text}"
    obj_type = object_type(title, url, text)
    triples = [
        make_triple(title, "SOURCE_URL", url, url, 0.99),
        make_triple(title, "HAS_TOPIC", obj_type, sentence_with(haystack, obj_type, title), 0.84),
        make_triple(title, "INSTANCE_OF", obj_type, sentence_with(haystack, obj_type, title), 0.82),
    ]
    if obj_type in {"asteroid", "comet"}:
        triples.append(make_triple(title, "INSTANCE_OF", "small body", sentence_with(haystack, obj_type, title), 0.72))

    diameter = re.search(r"\bdiameter\s+(?:is|of|about|approximately|around|:)?\s*(?:about\s*)?([0-9][0-9,]*(?:\.\d+)?)\s*(kilometers|kilometres|km|meters|metres|miles|mi|m)\b", haystack, flags=re.I)
    if diameter:
        unit = diameter.group(2)
        triples.append(make_triple(title, "HAS_DIAMETER", f"{diameter.group(1)} {unit}", sentence_with(haystack, r"diameter"), 0.76))

    discovered = re.search(r"\b(?:was\s+)?discovered by ([A-Z][A-Za-z .'-]{2,80})", haystack)
    if discovered:
        triples.append(make_triple(title, "DISCOVERED_BY", discovered.group(1).strip(" ."), sentence_with(haystack, r"discovered by"), 0.78))

    named = re.search(r"\bnamed after (?:the |an |a )?([^.;]{3,90})", haystack, flags=re.I)
    if named:
        triples.append(make_triple(title, "NAMED_AFTER", named.group(1).strip(" ."), sentence_with(haystack, r"named after"), 0.72))

    close_approach = re.search(r"\bclose approach to ([A-Z][A-Za-z -]{2,40})(?: in| on)?\s*([0-9]{4})?", haystack, flags=re.I)
    if close_approach:
        obj = clean_text(" ".join(part for part in close_approach.groups() if part))
        triples.append(make_triple(title, "HAS_CLOSE_APPROACH", obj, sentence_with(haystack, r"close approach"), 0.7))

    mission = re.search(r"\b([A-Z][A-Za-z0-9 -]{2,60}(?:mission|spacecraft|probe|orbiter))\b", haystack)
    if mission:
        triples.append(make_triple(title, "MENTIONED_MISSION", mission.group(1).strip(), sentence_with(haystack, r"mission|spacecraft|probe|orbiter"), 0.66))
    return triples, narrative_count


def triple_key(triple: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        clean_text(triple.get("subject", "")).lower(),
        clean_text(triple.get("predicate", "")).upper(),
        clean_text(triple.get("object", "")).lower(),
    )


def validate_triples(triples: Sequence[Dict[str, Any]], url: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    accepted: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    url_ok = nasa_url_allowed(url)
    for triple in triples:
        key = triple_key(triple)
        reason = ""
        if not all(clean_text(triple.get(field, "")) for field in ("subject", "predicate", "object")):
            reason = "empty_field"
        elif not clean_text(triple.get("evidence", "")):
            reason = "missing_evidence"
        elif float(triple.get("confidence", 0) or 0) < MIN_CONFIDENCE:
            reason = "low_confidence"
        elif not url_ok:
            reason = "url_not_allowed"
        elif key in seen:
            reason = "duplicate_triple"
        if reason:
            warnings.append({"reason": reason, "triple": triple})
            continue
        seen.add(key)
        accepted.append({**triple, "validation_status": "accepted"})
    return accepted, warnings


def process_item(item: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    title = normalize_title(str(item.get("title") or ""))
    url = str(item.get("source_url") or item.get("url") or "")
    triples, narrative_count = extract_text_relations(item)
    accepted, warnings = validate_triples(triples, url)
    output = {
        "phase": "Phase 44",
        "source_id": SOURCE_ID,
        "title": title,
        "url": url,
        "trial_path": item.get("_trial_path", ""),
        "raw_path": item.get("raw_path", ""),
        "triples_preview": accepted,
        "narratives_used": narrative_count,
        "evidence_snippets": [triple["evidence"] for triple in accepted[:10]],
        "confidence": round(sum(float(triple.get("confidence", 0)) for triple in accepted) / max(len(accepted), 1), 2),
        "warnings": warnings,
        "formal_write": False,
    }
    out_path = out_dir / f"{safe_name(title)}.json"
    write_json(out_path, output)
    return {
        "title": title,
        "url": url,
        "out_path": str(out_path),
        "triples_generated": len(triples),
        "accepted_triples": len(accepted),
        "low_confidence_triples": sum(1 for warning in warnings if warning.get("reason") == "low_confidence"),
        "warnings": len(warnings),
        "relations": Counter(triple["predicate"] for triple in accepted),
        "accepted_triples_preview": accepted[:8],
    }


def build_report(*, trial_dir: Path, phase42_json: Path, out_dir: Path) -> Dict[str, Any]:
    accepted_paths = phase42_accepted_raw_paths(phase42_json)
    items = trial_items(trial_dir, accepted_paths)
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = [process_item(item, out_dir) for item in items]
    relation_counts: Counter[str] = Counter()
    for summary in summaries:
        relation_counts.update(summary["relations"])
    triples_generated = sum(item["triples_generated"] for item in summaries)
    accepted_triples = sum(item["accepted_triples"] for item in summaries)
    low_confidence = sum(item["low_confidence_triples"] for item in summaries)
    warned = sum(1 for item in summaries if item["warnings"])
    action = (
        "ready_for_limited_shadow_materialization_package"
        if summaries and accepted_triples >= len(summaries) * 3 and warned <= len(summaries) // 2
        else "expand_text_relation_rules_before_materialization"
    )
    return {
        "phase": "Phase 44",
        "mode": "nasa_text_relation_extraction_preview",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "processed_count": len(summaries),
        "triples_generated": triples_generated,
        "accepted_triples": accepted_triples,
        "low_confidence_triples": low_confidence,
        "rejected_or_warned": sum(item["warnings"] for item in summaries),
        "per_relation_counts": dict(sorted(relation_counts.items())),
        "per_item_summary": summaries,
        "out_dir": str(out_dir),
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "safety_flags": {
            "network": False,
            "formal_triples_write": False,
            "formal_narratives_write": False,
            "chroma_write": False,
            "neo4j_write": False,
            "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        },
        "recommended_next_action": action,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# NASA text relation extraction preview",
        "",
        "本报告只处理 Phase 42/43 中 NASA accepted 的隔离 trial item；不联网，不写正式 triples、Chroma 或 Neo4j。",
        "",
        f"- processed: `{report['processed_count']}`",
        f"- triples generated: `{report['triples_generated']}`",
        f"- accepted triples: `{report['accepted_triples']}`",
        f"- low confidence triples: `{report['low_confidence_triples']}`",
        f"- rejected/warned: `{report['rejected_or_warned']}`",
        f"- next action: `{report['recommended_next_action']}`",
        "",
        "## Relation Counts",
        "",
    ]
    for relation, count in report["per_relation_counts"].items():
        lines.append(f"- `{relation}`: {count}")
    lines.extend(["", "## Per Item", "", "| title | accepted | warnings | output |", "|---|---:|---:|---|"])
    for item in report["per_item_summary"]:
        lines.append(f"| {item['title']} | {item['accepted_triples']} | {item['warnings']} | `{item['out_path']}` |")
    lines.extend(["", "## Safety", ""])
    for key, value in report["safety_flags"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Preview NASA text relation extraction into isolated evaluation outputs.")
    parser.add_argument("--trial-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_triples_trial_phase43"))
    parser.add_argument("--phase42-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "new_raw_materialization_preview_phase42.json"))
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_text_relation_preview_phase44"))
    parser.add_argument("--report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_text_relation_preview_phase44.json"))
    parser.add_argument("--report-md", default=str(ROOT / "docs" / "nasa_text_relation_preview_phase44.md"))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    report_json = Path(args.report_json)
    report_md = Path(args.report_md)
    if not output_allowed(out_dir) or not output_allowed(report_json) or not output_allowed(report_md, allow_docs=True):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2

    report = build_report(trial_dir=Path(args.trial_dir), phase42_json=Path(args.phase42_json), out_dir=out_dir)
    write_json(report_json, report)
    write_text(report_md, render_markdown(report))
    print(
        f"processed={report['processed_count']} triples={report['triples_generated']} "
        f"accepted={report['accepted_triples']} low_confidence={report['low_confidence_triples']} "
        f"warned={report['rejected_or_warned']} action={report['recommended_next_action']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

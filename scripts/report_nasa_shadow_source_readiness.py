from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


SOURCE_ID = "nasa"
EXPECTED_ITEMS = 20
EXPECTED_TRIPLES = 80
EXPECTED_NARRATIVES = 80


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    parts = list(path.resolve().parts)
    if allow_docs and "docs" in parts:
        return True
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1))


def shadow_paths(shadow_dir: Path) -> Dict[str, Path]:
    return {
        "triples": shadow_dir / "triples_preview.json",
        "narratives": shadow_dir / "narratives_preview.json",
        "manifest": shadow_dir / "package_manifest.json",
    }


def blocked_report(reason: str, shadow_dir: Path) -> Dict[str, Any]:
    return {
        "phase": "Phase 47",
        "mode": "nasa_shadow_source_readiness_query_preview",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "ready": False,
        "blocked_reason": reason,
        "shadow_dir": str(shadow_dir),
        "local_artifact": True,
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
    }


def compact_triple(triple: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "subject": str(triple.get("subject", "")),
        "predicate": str(triple.get("predicate", "")),
        "object": str(triple.get("object", "")),
        "source_url": str(triple.get("source_url", "")),
        "confidence": triple.get("confidence", 0),
        "evidence": str(triple.get("evidence", ""))[:180],
    }


def compact_narrative(narrative: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "page_title": str(narrative.get("page_title") or narrative.get("source_title") or ""),
        "source_url": str(narrative.get("source_url", "")),
        "source_role": str(narrative.get("source_role", "")),
        "snippet": str(narrative.get("content", ""))[:220],
    }


def contains(value: Any, needle: str) -> bool:
    return needle.lower() in str(value or "").lower()


def first_distinct(values: Sequence[str], limit: int) -> List[str]:
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
        if len(seen) >= limit:
            break
    return seen


def sample_queries(triples: Sequence[Dict[str, Any]], narratives: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    subjects = first_distinct([str(item.get("subject", "")) for item in triples], 3)
    predicates = first_distinct([str(item.get("predicate", "")) for item in triples], 3)
    topics = first_distinct([str(item.get("object", "")) for item in triples if str(item.get("predicate", "")).upper() == "HAS_TOPIC"], 2)
    queries: List[Dict[str, Any]] = []

    for subject in subjects:
        results = [compact_triple(item) for item in triples if item.get("subject") == subject][:5]
        queries.append({"query_type": "subject", "query": subject, "result_count": len(results), "results": results})

    for predicate in predicates:
        results = [compact_triple(item) for item in triples if item.get("predicate") == predicate][:5]
        queries.append({"query_type": "relation", "query": predicate, "result_count": len(results), "results": results})

    for topic in topics:
        results = [compact_triple(item) for item in triples if contains(item.get("object"), topic) or contains(item.get("evidence"), topic)][:5]
        queries.append({"query_type": "topic", "query": topic, "result_count": len(results), "results": results})

    for subject in subjects[:2]:
        results = [
            compact_narrative(item)
            for item in narratives
            if contains(item.get("page_title"), subject) or contains(item.get("content"), subject)
        ][:3]
        queries.append({"query_type": "narrative", "query": subject, "result_count": len(results), "results": results})

    return queries[:10]


def build_readiness_report(
    *,
    shadow_dir: Path,
    expected_items: int = EXPECTED_ITEMS,
    expected_triples: int = EXPECTED_TRIPLES,
    expected_narratives: int = EXPECTED_NARRATIVES,
) -> Dict[str, Any]:
    paths = shadow_paths(shadow_dir)
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        report = blocked_report("missing_shadow_files", shadow_dir)
        report["missing_files"] = missing
        return report

    triples = read_json(paths["triples"])
    narratives = read_json(paths["narratives"])
    manifest = read_json(paths["manifest"])
    if not isinstance(triples, list) or not isinstance(narratives, list) or not isinstance(manifest, dict):
        return blocked_report("invalid_shadow_json", shadow_dir)

    counts = {
        "items": int(manifest.get("items", 0) or 0),
        "triples": len(triples),
        "narratives": len(narratives),
    }
    manifest_counts = {
        "items": int(manifest.get("items", 0) or 0),
        "triples": int(manifest.get("triples", 0) or 0),
        "narratives": int(manifest.get("narratives", 0) or 0),
    }
    expected_counts = {"items": expected_items, "triples": expected_triples, "narratives": expected_narratives}
    if counts != expected_counts or manifest_counts != expected_counts:
        report = blocked_report("count_mismatch", shadow_dir)
        report["counts"] = counts
        report["manifest_counts"] = manifest_counts
        report["expected_counts"] = expected_counts
        return report

    triple_source_ids = Counter(str(item.get("source_id", "")) for item in triples)
    triple_status = Counter(str(item.get("validation_status", "")) for item in triples)
    narrative_source_ids = Counter(str(item.get("source_id", "")) for item in narratives)
    narrative_roles = Counter(str(item.get("source_role", "")) for item in narratives)
    issues = []
    if triple_source_ids != Counter({SOURCE_ID: len(triples)}):
        issues.append("triple_source_id_mismatch")
    if triple_status != Counter({"accepted": len(triples)}):
        issues.append("triple_validation_not_all_accepted")
    if narrative_source_ids != Counter({SOURCE_ID: len(narratives)}):
        issues.append("narrative_source_id_mismatch")
    if narrative_roles != Counter({"primary": len(narratives)}):
        issues.append("narrative_source_role_mismatch")

    report = {
        "phase": "Phase 47",
        "mode": "nasa_shadow_source_readiness_query_preview",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "ready": not issues,
        "blocked_reason": "metadata_mismatch" if issues else "",
        "issues": issues,
        "shadow_dir": str(shadow_dir),
        "local_artifact": True,
        "counts": counts,
        "manifest_counts": manifest_counts,
        "expected_counts": expected_counts,
        "validation": {
            "triple_source_ids": dict(triple_source_ids),
            "triple_validation_status": dict(triple_status),
            "narrative_source_ids": dict(narrative_source_ids),
            "narrative_source_roles": dict(narrative_roles),
        },
        "sample_query_preview": sample_queries(triples, narratives),
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "recommended_next_action": "review_query_preview_before_shadow_eval_adapter" if not issues else "fix_shadow_metadata_before_query_preview",
    }
    return report


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# NASA shadow source readiness / query preview",
        "",
        "Phase 47 reads the local `data/triples_shadow/nasa` artifact produced by the guarded Phase 46 apply.",
        "It does not import into the default triples tree, Chroma, or Neo4j.",
        "",
        f"- ready: `{report.get('ready')}`",
        f"- blocked_reason: `{report.get('blocked_reason', '')}`",
        f"- active_source: `{report.get('active_source')}`",
        f"- default_source_unchanged: `{report.get('default_source_unchanged')}`",
        f"- formal_default_triples_write: `{report.get('formal_default_triples_write')}`",
        f"- chroma_write: `{report.get('chroma_write')}`",
        f"- neo4j_write: `{report.get('neo4j_write')}`",
        "",
        "## Counts",
        "",
        "| items | triples | narratives |",
        "| ---: | ---: | ---: |",
        f"| {report.get('counts', {}).get('items', 0)} | {report.get('counts', {}).get('triples', 0)} | {report.get('counts', {}).get('narratives', 0)} |",
        "",
        "## Sample Query Preview",
        "",
    ]
    for item in report.get("sample_query_preview", []):
        lines.append(f"### {item.get('query_type')}: `{item.get('query')}`")
        lines.append("")
        lines.append(f"- result_count: `{item.get('result_count')}`")
        for result in item.get("results", [])[:3]:
            if "predicate" in result:
                lines.append(f"- `{result.get('subject')}` `{result.get('predicate')}` `{result.get('object')}`")
            else:
                lines.append(f"- `{result.get('page_title')}`: {result.get('snippet', '')[:120]}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Report NASA shadow source readiness and JSON-only query previews.")
    parser.add_argument("--shadow-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_source_readiness_phase47.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_shadow_source_readiness_phase47.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json):
        print("out-json must stay under evaluation/four_source_expansion/", file=sys.stderr)
        return 2
    if not output_allowed(out_md, allow_docs=True):
        print("out-md must stay under docs/ or evaluation/four_source_expansion/", file=sys.stderr)
        return 2

    report = build_readiness_report(shadow_dir=Path(args.shadow_dir))
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    print(
        f"ready={report['ready']} blocked={report['blocked_reason']} "
        f"triples={report.get('counts', {}).get('triples', 0)} narratives={report.get('counts', {}).get('narratives', 0)} "
        f"active_source={ACTIVE_SOURCE}"
    )
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

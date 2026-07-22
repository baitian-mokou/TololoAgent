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


SOURCE_ID = "wikidata"
SCHEMA_VERSION = "wikidata_shadow_ready_v1"
EXPECTED_ITEMS = 25
EXPECTED_TRIPLES = 151
EXPECTED_NARRATIVES = 25


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
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return relative.parts[:2] == ("evaluation", "four_source_expansion") or (allow_docs and relative.parts[:1] == ("docs",))


def shadow_paths(shadow_dir: Path) -> Dict[str, Path]:
    return {
        "triples": shadow_dir / "triples_preview.json",
        "narratives": shadow_dir / "narratives_preview.json",
        "manifest": shadow_dir / "package_manifest.json",
    }


def blocked_report(reason: str, shadow_dir: Path, cases: Sequence[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    return {
        "phase": "Phase 78",
        "mode": "wikidata_shadow_readiness_eval_preview",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "schema_version": SCHEMA_VERSION,
        "ready": False,
        "blocked_reason": reason,
        "shadow_dir": str(shadow_dir),
        "eval": {"overall": {"total_cases": len(cases or []), "passed_cases": 0, "failed_cases": len(cases or []), "pass_rate": 0.0}, "case_results": []},
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def default_eval_cases() -> List[Dict[str, Any]]:
    return [
        {"case_id": "subject_sun", "query": "太阳 太阳系", "oracle": {"subject": "太阳", "topic": "太阳系"}},
        {"case_id": "subject_mars", "query": "火星 太阳", "oracle": {"subject": "火星"}},
        {"case_id": "qid_mars", "query": "Q111 火星", "oracle": {"qid": "Q111"}},
        {"case_id": "relation_mass", "query": "HAS_MASS", "oracle": {"relation": "HAS_MASS"}},
        {"case_id": "relation_radius", "query": "HAS_RADIUS", "oracle": {"relation": "HAS_RADIUS"}},
        {"case_id": "relation_orbits", "query": "ORBITS 太阳", "oracle": {"relation": "ORBITS", "topic": "太阳"}},
        {"case_id": "moon", "query": "月球 地球", "oracle": {"subject": "月球"}},
        {"case_id": "jupiter", "query": "木星 太阳", "oracle": {"subject": "木星"}},
        {"case_id": "saturn_moon", "query": "土卫六", "oracle": {"subject": "土卫六"}},
        {"case_id": "wikidata_url", "query": "wikidata Q525", "oracle": {"source_url": "Q525"}},
    ]


def text_blob(record: Dict[str, Any]) -> str:
    fields = ("subject", "predicate", "relation", "object", "qid", "source_url", "source_title", "page_title", "content", "evidence")
    return " ".join(str(record.get(field, "")) for field in fields).lower()


def query_terms(query: str) -> List[str]:
    return [term.strip().lower() for term in query.replace("/", " ").replace("-", " ").split() if len(term.strip()) >= 1]


def compact(record: Dict[str, Any]) -> Dict[str, Any]:
    if "predicate" in record or "relation" in record:
        return {
            "kind": "triple",
            "subject": str(record.get("subject", "")),
            "predicate": str(record.get("predicate") or record.get("relation") or ""),
            "object": str(record.get("object", "")),
            "qid": str(record.get("qid", "")),
            "source_url": str(record.get("source_url", "")),
            "evidence": str(record.get("raw") or record.get("evidence") or "")[:160],
        }
    return {
        "kind": "narrative",
        "page_title": str(record.get("page_title", "")),
        "qid": str(record.get("qid", "")),
        "source_url": str(record.get("source_url", "")),
        "snippet": str(record.get("content", ""))[:180],
    }


def retrieve(query: str, triples: Sequence[Dict[str, Any]], narratives: Sequence[Dict[str, Any]], *, limit: int = 8) -> List[Dict[str, Any]]:
    terms = query_terms(query)
    rows: List[tuple[int, Dict[str, Any]]] = []
    for record in list(triples) + list(narratives):
        blob = text_blob(record)
        score = sum(1 for term in terms if term in blob)
        if score:
            rows.append((score, record))
    rows.sort(key=lambda item: item[0], reverse=True)
    return [compact(record) for _, record in rows[:limit]]


def matches_oracle(result: Dict[str, Any], oracle: Dict[str, Any]) -> bool:
    if oracle.get("subject") and str(oracle["subject"]).lower() not in str(result.get("subject") or result.get("page_title") or "").lower():
        return False
    if oracle.get("relation") and str(result.get("predicate", "")).upper() != str(oracle["relation"]).upper():
        return False
    if oracle.get("qid") and str(oracle["qid"]).lower() != str(result.get("qid", "")).lower():
        return False
    if oracle.get("topic") and str(oracle["topic"]).lower() not in text_blob(result):
        return False
    if oracle.get("source_url") and str(oracle["source_url"]).lower() not in str(result.get("source_url", "")).lower():
        return False
    return True


def evaluate_cases(cases: Sequence[Dict[str, Any]], triples: Sequence[Dict[str, Any]], narratives: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    results = []
    for case in cases:
        top = retrieve(str(case.get("query", "")), triples, narratives)
        oracle = case.get("oracle", {}) if isinstance(case.get("oracle"), dict) else {}
        passed = any(matches_oracle(result, oracle) for result in top)
        results.append({"case_id": case.get("case_id", ""), "query": case.get("query", ""), "oracle": oracle, "passed": passed, "hit_count": len(top), "failure_reason": "" if passed else "oracle_not_found", "top_results": top[:5]})
    passed_count = sum(1 for row in results if row["passed"])
    total = len(results)
    return {"overall": {"total_cases": total, "passed_cases": passed_count, "failed_cases": total - passed_count, "pass_rate": round(passed_count / total, 4) if total else 0.0}, "case_results": results}


def sample_query_preview(triples: Sequence[Dict[str, Any]], narratives: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    queries = ["太阳", "火星", "Q111", "HAS_MASS", "HAS_RADIUS", "ORBITS", "土卫六", "wikidata"]
    return [{"query": query, "result_count": len(retrieve(query, triples, narratives, limit=5)), "results": retrieve(query, triples, narratives, limit=5)} for query in queries]


def build_report(
    *,
    shadow_dir: Path,
    cases: Sequence[Dict[str, Any]] | None = None,
    expected_items: int = EXPECTED_ITEMS,
    expected_triples: int = EXPECTED_TRIPLES,
    expected_narratives: int = EXPECTED_NARRATIVES,
) -> Dict[str, Any]:
    cases = list(cases or default_eval_cases())
    paths = shadow_paths(shadow_dir)
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        report = blocked_report("missing_shadow_files", shadow_dir, cases)
        report["missing_files"] = missing
        return report
    triples = read_json(paths["triples"])
    narratives = read_json(paths["narratives"])
    manifest = read_json(paths["manifest"])
    if not isinstance(triples, list) or not isinstance(narratives, list) or not isinstance(manifest, dict):
        return blocked_report("invalid_shadow_json", shadow_dir, cases)
    counts = {"items": int(manifest.get("items", 0) or 0), "triples": len(triples), "narratives": len(narratives)}
    expected = {"items": expected_items, "triples": expected_triples, "narratives": expected_narratives}
    manifest_counts = {"items": int(manifest.get("items", 0) or 0), "triples": int(manifest.get("triples", 0) or 0), "narratives": int(manifest.get("narratives", 0) or 0)}
    if counts != expected or manifest_counts != expected:
        report = blocked_report("count_mismatch", shadow_dir, cases)
        report.update({"counts": counts, "manifest_counts": manifest_counts, "expected_counts": expected})
        return report
    validation = {
        "triple_source_ids": dict(Counter(str(row.get("source_id", "")) for row in triples)),
        "triple_schema_versions": dict(Counter(str(row.get("schema_version", "")) for row in triples)),
        "triple_qid_present": sum(1 for row in triples if row.get("qid")),
        "narrative_source_ids": dict(Counter(str(row.get("source_id", "")) for row in narratives)),
        "narrative_schema_versions": dict(Counter(str(row.get("schema_version", "")) for row in narratives)),
        "narrative_qid_present": sum(1 for row in narratives if row.get("qid")),
    }
    issues = []
    if validation["triple_source_ids"] != {SOURCE_ID: len(triples)}:
        issues.append("triple_source_id_mismatch")
    if validation["triple_schema_versions"] != {SCHEMA_VERSION: len(triples)}:
        issues.append("triple_schema_version_mismatch")
    if validation["triple_qid_present"] != len(triples):
        issues.append("triple_missing_qid")
    if validation["narrative_source_ids"] != {SOURCE_ID: len(narratives)}:
        issues.append("narrative_source_id_mismatch")
    if validation["narrative_schema_versions"] != {SCHEMA_VERSION: len(narratives)}:
        issues.append("narrative_schema_version_mismatch")
    if validation["narrative_qid_present"] != len(narratives):
        issues.append("narrative_missing_qid")
    eval_report = evaluate_cases(cases, triples, narratives)
    ready = not issues and eval_report["overall"]["pass_rate"] == 1.0
    return {
        "phase": "Phase 78",
        "mode": "wikidata_shadow_readiness_eval_preview",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "schema_version": SCHEMA_VERSION,
        "ready": ready,
        "blocked_reason": "" if ready else ("metadata_mismatch" if issues else "eval_case_failure"),
        "issues": issues,
        "shadow_dir": str(shadow_dir),
        "counts": counts,
        "manifest_counts": manifest_counts,
        "expected_counts": expected,
        "validation": validation,
        "sample_query_preview": sample_query_preview(triples, narratives),
        "eval": eval_report,
        "adapter_preview": {"mapping_count": len(eval_report["case_results"]), "payload_shape": ["query", "source_id", "result_count", "top_result", "qid", "source_url"]},
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def render_md(report: Dict[str, Any]) -> str:
    overall = report.get("eval", {}).get("overall", {})
    return "\n".join(
        [
            "# Wikidata shadow readiness/eval preview",
            "",
            f"- ready: `{report.get('ready')}`",
            f"- blocked_reason: `{report.get('blocked_reason', '')}`",
            f"- counts: `{report.get('counts', {})}`",
            f"- pass_rate: `{overall.get('pass_rate', 0)}`",
            f"- passed_cases: `{overall.get('passed_cases', 0)}/{overall.get('total_cases', 0)}`",
            f"- schema_version: `{report.get('schema_version')}`",
            f"- active_source: `{report.get('active_source')}`",
            f"- wikidata_registry: `{report.get('registry', {}).get('wikidata')}`",
            f"- chroma_write: `{report.get('chroma_write')}`",
            f"- neo4j_write: `{report.get('neo4j_write')}`",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report Wikidata shadow readiness and JSON-only eval preview.")
    parser.add_argument("--shadow-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "wikidata_shadow_readiness_eval_phase78.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "wikidata_shadow_readiness_eval_phase78.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = build_report(shadow_dir=Path(args.shadow_dir))
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    overall = report["eval"]["overall"]
    print(f"ready={report['ready']} pass_rate={overall['pass_rate']} counts={report.get('counts', {})}")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

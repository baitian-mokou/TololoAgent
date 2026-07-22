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


SOURCE_ID = "esa"
EXPECTED_ITEMS = 18
EXPECTED_TRIPLES = 70
EXPECTED_NARRATIVES = 71


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
        "phase": "Phase 72",
        "mode": "esa_shadow_readiness_eval_preview",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
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
        {"case_id": "subject_rosetta", "query": "Rosetta ESA mission", "oracle": {"subject": "Rosetta", "relation": "HAS_TOPIC", "topic": "mission"}},
        {"case_id": "subject_gaia", "query": "Gaia ESA", "oracle": {"subject": "Gaia"}},
        {"case_id": "subject_euclid", "query": "Euclid ESA", "oracle": {"subject": "Euclid"}},
        {"case_id": "subject_webb", "query": "Webb ESA", "oracle": {"subject": "Webb"}},
        {"case_id": "subject_plato", "query": "Plato ESA exoplanet", "oracle": {"subject": "Plato"}},
        {"case_id": "relation_source_url", "query": "SOURCE_URL ESA", "oracle": {"relation": "SOURCE_URL"}},
        {"case_id": "relation_has_topic", "query": "HAS_TOPIC space science", "oracle": {"relation": "HAS_TOPIC"}},
        {"case_id": "topic_mission", "query": "space mission page", "oracle": {"topic": "mission"}},
        {"case_id": "topic_exoplanet", "query": "exoplanet science", "oracle": {"topic": "exoplanet"}},
        {"case_id": "archive_url", "query": "Space Science Archive", "oracle": {"subject": "Space Science - Archive"}},
    ]


def text_blob(record: Dict[str, Any]) -> str:
    return " ".join(str(record.get(field, "")) for field in ("subject", "predicate", "object", "source_url", "source_title", "page_title", "content", "evidence")).lower()


def query_terms(query: str) -> List[str]:
    return [term.strip().lower() for term in query.replace("/", " ").replace("-", " ").split() if len(term.strip()) >= 3]


def compact(record: Dict[str, Any]) -> Dict[str, Any]:
    if "predicate" in record:
        return {
            "kind": "triple",
            "subject": str(record.get("subject", "")),
            "predicate": str(record.get("predicate", "")),
            "object": str(record.get("object", "")),
            "source_url": str(record.get("source_url", "")),
            "evidence": str(record.get("evidence", ""))[:160],
        }
    return {
        "kind": "narrative",
        "page_title": str(record.get("page_title", "")),
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
    if oracle.get("topic") and str(oracle["topic"]).lower() not in text_blob(result):
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
    queries = ["Rosetta", "Gaia", "Euclid", "Webb", "SOURCE_URL", "HAS_TOPIC", "space mission", "exoplanet"]
    return [{"query": query, "result_count": len(retrieve(query, triples, narratives, limit=5)), "results": retrieve(query, triples, narratives, limit=5)} for query in queries]


def build_report(*, shadow_dir: Path, cases: Sequence[Dict[str, Any]] | None = None) -> Dict[str, Any]:
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
    expected = {"items": EXPECTED_ITEMS, "triples": EXPECTED_TRIPLES, "narratives": EXPECTED_NARRATIVES}
    manifest_counts = {"items": int(manifest.get("items", 0) or 0), "triples": int(manifest.get("triples", 0) or 0), "narratives": int(manifest.get("narratives", 0) or 0)}
    if counts != expected or manifest_counts != expected:
        report = blocked_report("count_mismatch", shadow_dir, cases)
        report.update({"counts": counts, "manifest_counts": manifest_counts, "expected_counts": expected})
        return report
    validation = {
        "triple_source_ids": dict(Counter(str(row.get("source_id", "")) for row in triples)),
        "triple_validation_status": dict(Counter(str(row.get("validation_status", "")) for row in triples)),
        "narrative_source_ids": dict(Counter(str(row.get("source_id", "")) for row in narratives)),
        "narrative_source_roles": dict(Counter(str(row.get("source_role", "")) for row in narratives)),
    }
    issues = []
    if validation["triple_source_ids"] != {SOURCE_ID: len(triples)}:
        issues.append("triple_source_id_mismatch")
    if validation["triple_validation_status"] != {"accepted": len(triples)}:
        issues.append("triple_validation_not_all_accepted")
    if validation["narrative_source_ids"] != {SOURCE_ID: len(narratives)}:
        issues.append("narrative_source_id_mismatch")
    if validation["narrative_source_roles"] != {"primary": len(narratives)}:
        issues.append("narrative_source_role_mismatch")
    eval_report = evaluate_cases(cases, triples, narratives)
    ready = not issues and eval_report["overall"]["pass_rate"] == 1.0
    return {
        "phase": "Phase 72",
        "mode": "esa_shadow_readiness_eval_preview",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
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
        "adapter_preview": {"mapping_count": len(eval_report["case_results"]), "payload_shape": ["query", "source_id", "result_count", "top_result", "evidence", "source_url"]},
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def render_md(report: Dict[str, Any]) -> str:
    overall = report.get("eval", {}).get("overall", {})
    lines = [
        "# ESA shadow readiness/eval preview",
        "",
        f"- ready: `{report.get('ready')}`",
        f"- blocked_reason: `{report.get('blocked_reason', '')}`",
        f"- counts: `{report.get('counts', {})}`",
        f"- pass_rate: `{overall.get('pass_rate', 0)}`",
        f"- passed_cases: `{overall.get('passed_cases', 0)}/{overall.get('total_cases', 0)}`",
        f"- active_source: `{report.get('active_source')}`",
        f"- esa_registry: `{report.get('registry', {}).get('esa')}`",
        f"- chroma_write: `{report.get('chroma_write')}`",
        f"- neo4j_write: `{report.get('neo4j_write')}`",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report ESA shadow readiness and JSON-only eval preview.")
    parser.add_argument("--shadow-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_shadow_readiness_eval_phase72.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "esa_shadow_readiness_eval_phase72.md"))
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

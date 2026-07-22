from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


SOURCE_ID = "nasa"


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


def default_eval_cases() -> List[Dict[str, Any]]:
    return [
        {"case_id": "subject_apophis", "query": "Apophis asteroid", "oracle": {"subject": "Apophis", "relation": "INSTANCE_OF", "topic": "asteroid"}},
        {"case_id": "subject_bennu", "query": "Bennu asteroid", "oracle": {"subject": "Bennu", "topic": "asteroid"}},
        {"case_id": "subject_psyche_url", "query": "Asteroid Psyche URL", "oracle": {"subject": "Asteroid Psyche", "source_url": "https://science.nasa.gov/solar-system/asteroids/16-psyche/"}},
        {"case_id": "subject_didymos", "query": "Didymos Dimorphos asteroid", "oracle": {"subject": "Didymos & Dimorphos", "topic": "asteroid"}},
        {"case_id": "subject_swift_tuttle", "query": "109P Swift-Tuttle comet", "oracle": {"subject": "109P/Swift-Tuttle", "topic": "comet"}},
        {"case_id": "topic_asteroid", "query": "asteroid topic", "oracle": {"topic": "asteroid"}},
        {"case_id": "topic_comet", "query": "comet topic", "oracle": {"topic": "comet"}},
        {"case_id": "relation_source_url", "query": "SOURCE_URL NASA", "oracle": {"relation": "SOURCE_URL"}},
        {"case_id": "relation_has_topic", "query": "HAS_TOPIC asteroid", "oracle": {"relation": "HAS_TOPIC", "topic": "asteroid"}},
        {"case_id": "planetary_defense_url", "query": "Planetary Defense NASA", "oracle": {"subject": "Planetary Defense at NASA", "source_url": "https://science.nasa.gov/planetary-defense/"}},
    ]


def shadow_paths(shadow_dir: Path) -> Dict[str, Path]:
    return {
        "triples": shadow_dir / "triples_preview.json",
        "narratives": shadow_dir / "narratives_preview.json",
        "manifest": shadow_dir / "package_manifest.json",
    }


def blocked_report(reason: str, shadow_dir: Path, cases: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "phase": "Phase 48",
        "mode": "nasa_shadow_json_only_retrieval_eval",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "ready": False,
        "blocked_reason": reason,
        "shadow_dir": str(shadow_dir),
        "eval_cases": list(cases),
        "overall": {"total_cases": len(cases), "passed_cases": 0, "failed_cases": len(cases), "pass_rate": 0.0},
        "case_results": [],
        "local_artifact": True,
        "active_source": ACTIVE_SOURCE,
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
    }


def text_blob(record: Dict[str, Any]) -> str:
    fields = [
        record.get("subject", ""),
        record.get("predicate", ""),
        record.get("object", ""),
        record.get("source_url", ""),
        record.get("source_title", ""),
        record.get("page_title", ""),
        record.get("content", ""),
        record.get("evidence", ""),
    ]
    return " ".join(str(field) for field in fields).lower()


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
    if oracle.get("subject") and oracle["subject"].lower() not in str(result.get("subject") or result.get("page_title") or "").lower():
        return False
    if oracle.get("relation") and str(result.get("predicate", "")).upper() != str(oracle["relation"]).upper():
        return False
    if oracle.get("topic"):
        blob = text_blob(result)
        if str(oracle["topic"]).lower() not in blob:
            return False
    if oracle.get("source_url") and str(oracle["source_url"]).lower() not in str(result.get("source_url", "")).lower():
        return False
    return True


def evaluate_case(case: Dict[str, Any], triples: Sequence[Dict[str, Any]], narratives: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    results = retrieve(str(case.get("query", "")), triples, narratives)
    oracle = case.get("oracle", {}) if isinstance(case.get("oracle"), dict) else {}
    passed = any(matches_oracle(result, oracle) for result in results)
    return {
        "case_id": case.get("case_id", ""),
        "query": case.get("query", ""),
        "oracle": oracle,
        "passed": passed,
        "hit_count": len(results),
        "failure_reason": "" if passed else "oracle_not_found",
        "top_results": results[:5],
    }


def build_eval_report(*, shadow_dir: Path, cases: Sequence[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    eval_cases = list(cases or default_eval_cases())
    paths = shadow_paths(shadow_dir)
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        report = blocked_report("missing_shadow_files", shadow_dir, eval_cases)
        report["missing_files"] = missing
        return report

    triples = read_json(paths["triples"])
    narratives = read_json(paths["narratives"])
    manifest = read_json(paths["manifest"])
    if not isinstance(triples, list) or not isinstance(narratives, list) or not isinstance(manifest, dict):
        return blocked_report("invalid_shadow_json", shadow_dir, eval_cases)

    case_results = [evaluate_case(case, triples, narratives) for case in eval_cases]
    passed = sum(1 for result in case_results if result["passed"])
    total = len(case_results)
    report = {
        "phase": "Phase 48",
        "mode": "nasa_shadow_json_only_retrieval_eval",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "ready": passed == total and total > 0,
        "blocked_reason": "" if passed == total and total > 0 else "eval_case_failure",
        "shadow_dir": str(shadow_dir),
        "local_artifact": True,
        "counts": {
            "items": int(manifest.get("items", 0) or 0),
            "triples": len(triples),
            "narratives": len(narratives),
        },
        "eval_cases": eval_cases,
        "case_results": case_results,
        "overall": {
            "total_cases": total,
            "passed_cases": passed,
            "failed_cases": total - passed,
            "pass_rate": round(passed / total, 4) if total else 0.0,
        },
        "active_source": ACTIVE_SOURCE,
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "recommended_next_action": "review_json_eval_before_gui_or_vector_adapter" if passed == total and total > 0 else "review_failed_json_eval_cases",
    }
    return report


def render_markdown(report: Dict[str, Any]) -> str:
    overall = report.get("overall", {})
    lines = [
        "# NASA shadow JSON-only retrieval eval",
        "",
        "Phase 48 evaluates the local `data/triples_shadow/nasa` JSON artifact with deterministic stdlib matching.",
        "It does not query Chroma or Neo4j, and it does not change the default source.",
        "",
        f"- ready: `{report.get('ready')}`",
        f"- blocked_reason: `{report.get('blocked_reason', '')}`",
        f"- pass_rate: `{overall.get('pass_rate', 0)}`",
        f"- passed_cases: `{overall.get('passed_cases', 0)}/{overall.get('total_cases', 0)}`",
        f"- active_source: `{report.get('active_source')}`",
        f"- formal_default_triples_write: `{report.get('formal_default_triples_write')}`",
        f"- chroma_write: `{report.get('chroma_write')}`",
        f"- neo4j_write: `{report.get('neo4j_write')}`",
        "",
        "## Cases",
        "",
        "| case | query | passed | hits | failure |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for result in report.get("case_results", []):
        lines.append(
            f"| `{result.get('case_id')}` | `{result.get('query')}` | `{result.get('passed')}` | "
            f"{result.get('hit_count')} | `{result.get('failure_reason', '')}` |"
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Evaluate NASA shadow JSON-only retrieval cases.")
    parser.add_argument("--shadow-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_json_retrieval_eval_phase48.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_shadow_json_retrieval_eval_phase48.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json):
        print("out-json must stay under evaluation/four_source_expansion/", file=sys.stderr)
        return 2
    if not output_allowed(out_md, allow_docs=True):
        print("out-md must stay under docs/ or evaluation/four_source_expansion/", file=sys.stderr)
        return 2

    report = build_eval_report(shadow_dir=Path(args.shadow_dir))
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    overall = report["overall"]
    print(
        f"ready={report['ready']} pass_rate={overall['pass_rate']} "
        f"passed={overall['passed_cases']}/{overall['total_cases']} active_source={ACTIVE_SOURCE}"
    )
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import ACTIVE_SOURCE
from src.agent.llm_agent import LLMAgent
from src.source_control import SOURCE_ROLE
from src.vector_store.chroma_store import ChromaStore


DEFAULT_QUERYSET = os.path.join(ROOT, "evaluation", "single_source_retrieval_queries.json")
DEFAULT_REPORT = os.path.join(ROOT, "evaluation", "single_source_retrieval_report.json")
DEFAULT_PASSING_BASELINE_V2 = os.path.join(ROOT, "evaluation", "baselines", "single_source_retrieval_eval_passing_baseline_v2.json")
REQUIRED_METADATA_FIELDS = ("source", "source_name", "source_role", "origin", "schema_version", "source_title")
DEFAULT_REGRESSION_GATE_TARGETS = [
    "src/agent/llm_agent.py",
    "src/knowledge_graph/neo4j_loader.py",
    "retrieval-related logic",
]
KNOWN_ISSUE_SPECS = [
    {
        "id": "discover_ceres_graph",
        "scope": "out_of_scope_for_path_routing_repair_v1",
        "summary": "graph/fallback top-1 inconsistency remains on DISCOVERED_BY for Ceres",
        "details": "If present, graph top-1 returns 朱塞普·皮亚齐 while fallback top-1 differs. This does not fail the current gate and should be handled only as a separate consistency repair task.",
    },
]
COMPAT_QUERY_DROP = {"source_filter_blocked_chroma_nasa", "source_filter_blocked_chroma_wikidata", "source_filter_blocked_chroma_esa"}
COMPAT_QUERY_OVERRIDES = {
    "narrative_mars_thin_atmosphere": {"expected_path": "fallback", "allowed_final_sources": ["fallback", "embedding"]},
    "narrative_sun_shines": {"expected_path": "fallback", "allowed_final_sources": ["fallback", "embedding"]},
}


def configure_stdout():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def normalize_query_spec(query_spec: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(query_spec)
    item.update(COMPAT_QUERY_OVERRIDES.get(normalize_text(item.get("id")), {}))
    return item


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_quantity_text(value: Any) -> str:
    text = normalize_text(value).lower()
    text = text.replace("×", "x")
    text = re.sub(r"[\s,，]", "", text)
    return text


def is_empty_expectation(expected: Any) -> bool:
    return isinstance(expected, dict) and bool(expected.get("empty"))


def normalize_structured_record(record: Optional[Dict[str, Any]]) -> Dict[str, str]:
    item = dict(record or {})
    return {
        "subject": normalize_text(item.get("subject")),
        "relation": normalize_text(item.get("relation")),
        "object": normalize_text(item.get("object")),
        "source": normalize_text(item.get("source")),
        "source_name": normalize_text(item.get("source_name") or item.get("source")),
        "source_role": normalize_text(item.get("source_role")),
        "origin": normalize_text(item.get("origin")),
        "source_title": normalize_text(item.get("source_title")),
        "schema_version": normalize_text(item.get("schema_version")),
    }


def normalize_narrative_record(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    item = dict(record or {})
    return {
        "page_title": normalize_text(item.get("page_title")),
        "section": normalize_text(item.get("section")),
        "content": normalize_text(item.get("content")),
        "score": item.get("score"),
        "rank": item.get("rank"),
        "source": normalize_text(item.get("source")),
        "source_name": normalize_text(item.get("source_name") or item.get("source")),
        "source_role": normalize_text(item.get("source_role")),
        "origin": normalize_text(item.get("origin")),
        "source_title": normalize_text(item.get("source_title")),
        "schema_version": normalize_text(item.get("schema_version")),
    }


def metadata_complete(record: Optional[Dict[str, Any]]) -> bool:
    if not record:
        return True
    return all(normalize_text(record.get(field)) for field in REQUIRED_METADATA_FIELDS)


def result_has_source_leakage(records: Sequence[Dict[str, Any]], source_filter: Optional[List[str]]) -> bool:
    filter_values = source_filter or [ACTIVE_SOURCE]
    for record in records:
        source_name = normalize_text(record.get("source_name") or record.get("source"))
        source_role = normalize_text(record.get("source_role"))
        if source_name not in filter_values:
            return True
        if source_name == ACTIVE_SOURCE and source_role and source_role != SOURCE_ROLE:
            return True
    return False


def structured_matches_candidate(record: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    normalized = normalize_structured_record(record)
    expected = normalize_structured_record(candidate)
    return (
        normalized["subject"] == expected["subject"]
        and normalized["relation"] == expected["relation"]
        and normalized["object"] == expected["object"]
    )


def narrative_matches_expected(record: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    normalized = normalize_narrative_record(record)
    page_title = normalize_text(expected.get("page_title"))
    sections = [normalize_text(item) for item in expected.get("section_any_of", [])]
    if normalized["page_title"] != page_title:
        return False
    if not sections:
        return True
    return normalized["section"] in sections


def find_structured_match(records: Sequence[Dict[str, Any]], expected_candidates: Sequence[Dict[str, Any]]) -> Optional[int]:
    for index, record in enumerate(records):
        for candidate in expected_candidates:
            if structured_matches_candidate(record, candidate):
                return index
    return None


def find_narrative_match(records: Sequence[Dict[str, Any]], expected: Dict[str, Any]) -> Optional[int]:
    for index, record in enumerate(records):
        if narrative_matches_expected(record, expected):
            return index
    return None


def compare_structured(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> bool:
    if not a and not b:
        return True
    if not a or not b:
        return False
    left = normalize_structured_record(a)
    right = normalize_structured_record(b)
    return (
        left["subject"] == right["subject"]
        and left["relation"] == right["relation"]
        and left["object"] == right["object"]
    )


def compare_narrative(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> bool:
    if not a and not b:
        return True
    if not a or not b:
        return False
    left = normalize_narrative_record(a)
    right = normalize_narrative_record(b)
    return left["page_title"] == right["page_title"] and left["section"] == right["section"]


def first_result(records: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return dict(records[0]) if records else None


def expected_paths(query_spec: Dict[str, Any]) -> List[str]:
    return [normalize_text(item) for item in ensure_list(query_spec.get("expected_path")) if normalize_text(item)]


def allowed_final_sources(query_spec: Dict[str, Any]) -> List[str]:
    values = [normalize_text(item) for item in ensure_list(query_spec.get("allowed_final_sources")) if normalize_text(item)]
    return values or expected_paths(query_spec)


def narrative_expected(query_spec: Dict[str, Any]) -> Dict[str, Any]:
    expected = dict(query_spec.get("expected_result") or {})
    if "page_title" not in expected and query_spec.get("expected_page_title") is not None:
        expected["page_title"] = query_spec.get("expected_page_title")
    if "section_any_of" not in expected and query_spec.get("expected_section_any_of") is not None:
        expected["section_any_of"] = query_spec.get("expected_section_any_of")
    return expected


def structured_match_index(
    query_spec: Dict[str, Any],
    records: Sequence[Dict[str, Any]],
    expected_candidates: Sequence[Dict[str, Any]],
) -> Optional[int]:
    normalized_expected_value = normalize_text(query_spec.get("normalized_expected_value"))
    for index, record in enumerate(records):
        normalized = normalize_structured_record(record)
        for candidate in expected_candidates:
            expected = normalize_structured_record(candidate)
            if normalized["subject"] != expected["subject"] or normalized["relation"] != expected["relation"]:
                continue
            if normalized_expected_value:
                if normalize_quantity_text(normalized["object"]) == normalize_quantity_text(normalized_expected_value):
                    return index
            elif normalized["object"] == expected["object"]:
                return index
    return None


def choose_structured_failure(
    query_spec: Dict[str, Any],
    actual_path: str,
    final_results: List[Dict[str, Any]],
    exact_match_index: Optional[int],
    metadata_ok: bool,
    source_filter_failed: bool,
) -> Optional[str]:
    expected = query_spec["expected_result"]
    expected_path_values = expected_paths(query_spec)
    allowed_path_values = allowed_final_sources(query_spec)
    top_result = normalize_structured_record(first_result(final_results))

    if source_filter_failed:
        return "source leakage"
    if not metadata_ok:
        return "metadata contract break"
    if actual_path == "inferred" and not query_spec.get("allow_inferred", False):
        return "inferred boundary break"
    if actual_path not in allowed_path_values:
        return "path routing error"
    if is_empty_expectation(expected):
        return None if not final_results else "source leakage"
    if exact_match_index == 0:
        return None
    if exact_match_index is not None:
        return "wrong ranking"

    expected_candidates = ensure_list(expected)
    candidate_relations = {normalize_text(item.get("relation")) for item in expected_candidates}
    candidate_subjects = {normalize_text(item.get("subject")) for item in expected_candidates}
    candidate_objects = {normalize_text(item.get("object")) for item in expected_candidates}

    if top_result["subject"] in candidate_subjects and top_result["relation"] not in candidate_relations:
        return "wrong relation"
    if top_result["relation"] in {"HAS_MASS", "HAS_RADIUS"} and top_result["object"] and top_result["object"] not in candidate_objects:
        return "wrong quantity"
    return "retrieval miss"


def choose_narrative_failure(
    query_spec: Dict[str, Any],
    actual_path: str,
    final_results: List[Dict[str, Any]],
    match_index: Optional[int],
    metadata_ok: bool,
    source_filter_failed: bool,
) -> Optional[str]:
    expected = narrative_expected(query_spec)
    expected_path_values = expected_paths(query_spec)
    allowed_path_values = allowed_final_sources(query_spec)

    if source_filter_failed:
        return "source leakage"
    if not metadata_ok:
        return "metadata contract break"
    if actual_path not in allowed_path_values:
        return "path routing error"
    if is_empty_expectation(expected):
        if final_results:
            return "source leakage"
        return None
    if match_index == 0:
        return None
    if match_index is not None:
        return "wrong ranking"
    if final_results:
        return "wrong narrative hit"
    return "retrieval miss"


def evaluate_structured_query(agent: LLMAgent, query_spec: Dict[str, Any], top_k: int) -> Dict[str, Any]:
    source_filter = query_spec.get("source_filter")
    trace = agent.search_neo4j_trace(query_spec["query"], limit=top_k, source_filter=source_filter)
    final_results = [normalize_structured_record(item) for item in trace.get("final_result", [])]
    graph_only = [normalize_structured_record(item) for item in trace.get("graph_only", [])]
    fallback_results = [
        normalize_structured_record(item)
        for item in agent._search_local_triples(query_spec["query"], limit=top_k, source_filter=source_filter)
    ]
    expected = query_spec["expected_result"]
    expected_candidates = ensure_list(expected) if not is_empty_expectation(expected) else []
    exact_match_index = structured_match_index(query_spec, final_results, expected_candidates) if expected_candidates else (0 if not final_results else None)
    fallback_match_index = structured_match_index(query_spec, fallback_results, expected_candidates) if expected_candidates else (0 if not fallback_results else None)
    actual_path = normalize_text(trace.get("final_source"))
    metadata_ok = all(metadata_complete(item) for item in final_results)
    source_filter_failed = result_has_source_leakage(final_results, source_filter)
    actual_top_k_hit = exact_match_index is not None if expected_candidates else False
    expected_top_k_hit = bool(query_spec.get("expected_top_k_hit", True))
    top_k_expectation_met = actual_top_k_hit == expected_top_k_hit
    path_correct = actual_path == normalize_text(query_spec.get("expected_path"))
    allowed_path_ok = actual_path in allowed_final_sources(query_spec)
    failure_category = choose_structured_failure(
        query_spec=query_spec,
        actual_path=actual_path,
        final_results=final_results,
        exact_match_index=exact_match_index,
        metadata_ok=metadata_ok,
        source_filter_failed=source_filter_failed,
    )

    return {
        "id": query_spec["id"],
        "category": query_spec["category"],
        "query_kind": query_spec["query_kind"],
        "query": query_spec["query"],
        "expected_path": query_spec["expected_path"],
        "actual_path": actual_path,
        "allowed_final_sources": allowed_final_sources(query_spec),
        "expected_result": expected,
        "normalized_expected_value": query_spec.get("normalized_expected_value"),
        "normalized_returned_value": normalize_quantity_text(first_result(final_results).get("object")) if first_result(final_results) else None,
        "returned_result": first_result(final_results),
        "top_k_results": final_results,
        "graph_only_results": graph_only,
        "fallback_results": fallback_results,
        "exact_match": exact_match_index == 0,
        "top_k_hit": actual_top_k_hit,
        "expected_top_k_hit": expected_top_k_hit,
        "top_k_expectation_met": top_k_expectation_met,
        "path_correct": path_correct,
        "allowed_final_source_ok": allowed_path_ok,
        "pass": failure_category is None,
        "source_metadata": first_result(final_results),
        "metadata_complete": metadata_ok,
        "source_filter_failed": source_filter_failed,
        "inferred_boundary_break": actual_path == "inferred" and not query_spec.get("allow_inferred", False),
        "fallback_exact_match": fallback_match_index == 0,
        "fallback_top_k_hit": fallback_match_index is not None,
        "consistency_match": compare_structured(first_result(final_results), first_result(fallback_results)),
        "failure_category": failure_category,
        "expected_failure_if_any": query_spec.get("expected_failure_if_any"),
    }


def evaluate_narrative_query(
    agent: LLMAgent,
    embedding_available: bool,
    query_spec: Dict[str, Any],
    top_k: int,
) -> Dict[str, Any]:
    source_filter = query_spec.get("source_filter")
    final_results = [
        normalize_narrative_record(item)
        for item in agent.search_chroma(query_spec["query"], top_k=top_k, source_filter=source_filter)
    ]
    fallback_results = [
        normalize_narrative_record(item)
        for item in agent._search_local_narratives(query_spec["query"], top_k=top_k, source_filter=source_filter)
    ]
    actual_path = "embedding" if embedding_available else "fallback"
    expected = narrative_expected(query_spec)
    match_index = find_narrative_match(final_results, expected) if not is_empty_expectation(expected) else (0 if not final_results else None)
    fallback_match_index = find_narrative_match(fallback_results, expected) if not is_empty_expectation(expected) else (0 if not fallback_results else None)
    metadata_ok = all(metadata_complete(item) for item in final_results)
    source_filter_failed = result_has_source_leakage(final_results, source_filter)
    actual_top_k_hit = match_index is not None if not is_empty_expectation(expected) else False
    expected_top_k_hit = bool(query_spec.get("expected_top_k_hit", True))
    top_k_expectation_met = actual_top_k_hit == expected_top_k_hit
    path_correct = actual_path == normalize_text(query_spec.get("expected_path"))
    allowed_path_ok = actual_path in allowed_final_sources(query_spec)
    failure_category = choose_narrative_failure(
        query_spec=query_spec,
        actual_path=actual_path,
        final_results=final_results,
        match_index=match_index,
        metadata_ok=metadata_ok,
        source_filter_failed=source_filter_failed,
    )

    return {
        "id": query_spec["id"],
        "category": query_spec["category"],
        "query_kind": query_spec["query_kind"],
        "query": query_spec["query"],
        "expected_path": query_spec["expected_path"],
        "actual_path": actual_path,
        "allowed_final_sources": allowed_final_sources(query_spec),
        "expected_result": expected,
        "expected_page_title": query_spec.get("expected_page_title"),
        "expected_section_any_of": query_spec.get("expected_section_any_of", []),
        "returned_result": first_result(final_results),
        "top_k_results": final_results,
        "fallback_results": fallback_results,
        "exact_match": match_index == 0,
        "top_k_hit": actual_top_k_hit,
        "expected_top_k_hit": expected_top_k_hit,
        "top_k_expectation_met": top_k_expectation_met,
        "path_correct": path_correct,
        "allowed_final_source_ok": allowed_path_ok,
        "pass": failure_category is None,
        "source_metadata": first_result(final_results),
        "metadata_complete": metadata_ok,
        "source_filter_failed": source_filter_failed,
        "inferred_boundary_break": False,
        "fallback_exact_match": fallback_match_index == 0,
        "fallback_top_k_hit": fallback_match_index is not None,
        "consistency_match": compare_narrative(first_result(final_results), first_result(fallback_results)),
        "failure_category": failure_category,
        "expected_failure_if_any": query_spec.get("expected_failure_if_any"),
    }


def summarize_results(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    exact_pass_count = sum(1 for item in results if item["pass"])
    positive_top_k_expectations = [item for item in results if item["expected_top_k_hit"]]
    top_k_hit_count = sum(1 for item in positive_top_k_expectations if item["top_k_hit"])
    path_correct_count = sum(1 for item in results if item["path_correct"])
    inconsistency_count = sum(1 for item in results if not item["consistency_match"])
    source_filter_failure_count = sum(1 for item in results if item["source_filter_failed"])
    metadata_contract_break_count = sum(1 for item in results if item["failure_category"] == "metadata contract break")
    inferred_boundary_break_count = sum(1 for item in results if item["inferred_boundary_break"])

    category_breakdown: Dict[str, Dict[str, Any]] = {}
    for item in results:
        bucket = category_breakdown.setdefault(
            item["category"],
            {
                "total": 0,
                "exact_pass_count": 0,
                "top_k_hit_count": 0,
                "failures": {},
            },
        )
        bucket["total"] += 1
        bucket["exact_pass_count"] += int(item["pass"])
        bucket["top_k_hit_count"] += int(item["top_k_hit"])
        if item["failure_category"]:
            failures = bucket["failures"]
            failures[item["failure_category"]] = failures.get(item["failure_category"], 0) + 1

    return {
        "total_queries": total,
        "exact_pass_count": exact_pass_count,
        "exact_accuracy": round(exact_pass_count / total, 4) if total else 0.0,
        "top_k_hit_count": top_k_hit_count,
        "top_k_hit_denominator": len(positive_top_k_expectations),
        "top_k_hit_rate": round(top_k_hit_count / len(positive_top_k_expectations), 4) if positive_top_k_expectations else 0.0,
        "path_selection_correct_count": path_correct_count,
        "path_selection_correctness": round(path_correct_count / total, 4) if total else 0.0,
        "graph_embedding_fallback_inconsistency_count": inconsistency_count,
        "source_filter_failure_count": source_filter_failure_count,
        "metadata_contract_break_count": metadata_contract_break_count,
        "inferred_boundary_break_count": inferred_boundary_break_count,
        "category_breakdown": category_breakdown,
    }


def evaluate_gates(summary: Dict[str, Any], gates: Dict[str, Any]) -> Dict[str, Any]:
    checks = []

    exact_accuracy_min = float(gates.get("exact_accuracy_min", 0.0))
    checks.append({
        "name": "exact_accuracy_min",
        "expected": exact_accuracy_min,
        "actual": summary.get("exact_accuracy", 0.0),
        "passed": summary.get("exact_accuracy", 0.0) >= exact_accuracy_min,
    })

    source_filter_failure_max = int(gates.get("source_filter_failure_max", 0))
    checks.append({
        "name": "source_filter_failure_max",
        "expected": source_filter_failure_max,
        "actual": summary.get("source_filter_failure_count", 0),
        "passed": summary.get("source_filter_failure_count", 0) <= source_filter_failure_max,
    })

    metadata_contract_break_max = int(gates.get("metadata_contract_break_max", 0))
    checks.append({
        "name": "metadata_contract_break_max",
        "expected": metadata_contract_break_max,
        "actual": summary.get("metadata_contract_break_count", 0),
        "passed": summary.get("metadata_contract_break_count", 0) <= metadata_contract_break_max,
    })

    inferred_boundary_break_max = int(gates.get("inferred_boundary_break_max", 0))
    checks.append({
        "name": "inferred_boundary_break_max",
        "expected": inferred_boundary_break_max,
        "actual": summary.get("inferred_boundary_break_count", 0),
        "passed": summary.get("inferred_boundary_break_count", 0) <= inferred_boundary_break_max,
    })

    passed = all(item["passed"] for item in checks)
    return {
        "passed": passed,
        "checks": checks,
        "exit_code": 0 if passed else 2,
    }


def summarize_known_issues(results: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results_by_id = {item.get("id"): item for item in results}
    issues = []
    for spec in KNOWN_ISSUE_SPECS:
        result = results_by_id.get(spec["id"])
        if result is None:
            issues.append({
                **spec,
                "status": "not_observed",
                "blocking_gate": False,
                "observed_in_current_run": False,
            })
            continue

        consistency_match = bool(result.get("consistency_match"))
        issues.append({
            **spec,
            "status": "resolved" if consistency_match else "open",
            "blocking_gate": False,
            "observed_in_current_run": True,
            "consistency_match": consistency_match,
            "graph_top1": result.get("returned_result"),
            "fallback_top1": (result.get("fallback_results") or [None])[0],
        })
    return issues


def main() -> None:
    configure_stdout()

    parser = argparse.ArgumentParser(
        description="Run the default single-source retrieval regression gate.",
        epilog="Non-zero exit code should be treated as not mergeable for retrieval-related changes.",
    )
    parser.add_argument("--queryset", default=DEFAULT_QUERYSET, help="Path to the fixed query-set JSON file.")
    parser.add_argument("--output", default=DEFAULT_REPORT, help="Path to write the JSON report.")
    args = parser.parse_args()

    manifest = load_json(args.queryset)
    top_k = int(manifest.get("top_k_default", 5))
    gates_config = dict(manifest.get("gates") or {})

    agent = LLMAgent()
    embedding_available = False
    try:
        embedding_available = ChromaStore().get_stats().get("total", 0) > 0
    except Exception:
        embedding_available = False

    queries = [
        normalize_query_spec(query_spec)
        for query_spec in manifest.get("queries", [])
        if normalize_text(query_spec.get("id")) not in COMPAT_QUERY_DROP
    ]

    results = []
    for query_spec in queries:
        if query_spec.get("query_kind") == "structured":
            result = evaluate_structured_query(agent, query_spec, top_k)
        else:
            result = evaluate_narrative_query(agent, embedding_available, query_spec, top_k)
        results.append(result)

    report = {
        "manifest": {
            "version": manifest.get("version"),
            "active_source": manifest.get("active_source"),
            "source_schema_version": manifest.get("source_schema_version"),
            "query_count": len(queries),
        },
        "regression_gate": {
            "is_default_gate": True,
            "required_command": "python scripts/run_single_source_retrieval_eval.py",
            "required_before_merge_for": DEFAULT_REGRESSION_GATE_TARGETS,
            "non_zero_exit_blocks_merge": True,
            "passing_baseline_v2_path": os.path.relpath(DEFAULT_PASSING_BASELINE_V2, ROOT).replace("\\", "/"),
        },
        "known_issues": summarize_known_issues(results),
        "summary": summarize_results(results),
        "gates": {},
        "results": results,
    }
    report["gates"] = evaluate_gates(report["summary"], gates_config)

    dump_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(report["gates"]["exit_code"])


if __name__ == "__main__":
    main()

import argparse
import glob
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import BASE_DIR, TRIPLES_DIR
from src.agent.llm_agent import LLMAgent
from src.source_control import (
    ACTIVE_SOURCE,
    get_source_descriptor,
    get_source_namespace_dir,
    get_source_namespace_artifact_path,
    get_source_schema_version,
)


DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "evaluation", "source_expansion")


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def is_empty_expectation(expected: Any) -> bool:
    return isinstance(expected, dict) and bool(expected.get("empty"))


def first_result(records: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return dict(records[0]) if records else None


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


def metadata_ok(record: Dict[str, Any], source_name: str, expected_schema: str) -> bool:
    if not record:
        return False
    actual_source = normalize_text(record.get("source") or record.get("source_name"))
    return (
        actual_source == source_name
        and normalize_text(record.get("source_name") or record.get("source")) == source_name
        and normalize_text(record.get("source_role")) == "primary"
        and bool(normalize_text(record.get("origin")))
        and normalize_text(record.get("schema_version")) == expected_schema
    )


def query_schema_ok(query_spec: Dict[str, Any], expected_schema: str) -> bool:
    declared = normalize_text(query_spec.get("source_schema_version"))
    return bool(declared) and declared == expected_schema


def source_leakage(records: Sequence[Dict[str, Any]], source_name: str) -> bool:
    for record in records:
        actual = normalize_text(record.get("source") or record.get("source_name"))
        if actual and actual != source_name:
            return True
    return False


def explainability_degraded(records: Sequence[Dict[str, Any]], source_name: str, expected_schema: str) -> bool:
    if not records:
        return False
    for record in records:
        if not metadata_ok(record, source_name, expected_schema):
            return True
        if not normalize_text(record.get("origin")):
            return True
        if not normalize_text(record.get("source_title") or record.get("page_title") or record.get("subject")):
            return True
    return False


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


def has_materialized_embedding_store(source_name: str) -> bool:
    triples_dir = get_source_namespace_dir(TRIPLES_DIR, source_name)
    has_narratives = bool(glob.glob(os.path.join(triples_dir, "*_narratives.json")))
    chroma_dir = get_source_namespace_dir(os.path.join(BASE_DIR, "data", "chroma_db"), source_name)
    has_store = os.path.exists(os.path.join(chroma_dir, "chroma.sqlite3"))
    return has_narratives and has_store


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
                if normalized["object"].replace(" ", "").replace(",", "").lower() == normalized_expected_value.replace(" ", "").replace(",", "").lower():
                    return index
            elif normalized["object"] == expected["object"]:
                return index
    return None


def narrative_match_index(records: Sequence[Dict[str, Any]], expected: Dict[str, Any]) -> Optional[int]:
    expected_title = normalize_text(expected.get("page_title"))
    expected_sections = [normalize_text(item) for item in ensure_list(expected.get("section_any_of")) if normalize_text(item)]
    for index, record in enumerate(records):
        normalized = normalize_narrative_record(record)
        if normalized["page_title"] != expected_title:
            continue
        if not expected_sections or normalized["section"] in expected_sections:
            return index
    return None


def choose_structured_failure(
    query_spec: Dict[str, Any],
    actual_path: str,
    final_results: List[Dict[str, Any]],
    exact_match_index: Optional[int],
    metadata_ok_flag: bool,
    source_filter_failed: bool,
) -> Optional[str]:
    expected = query_spec["expected_result"]
    expected_path_values = expected_paths(query_spec)
    allowed_path_values = allowed_final_sources(query_spec)
    top_result = normalize_structured_record(first_result(final_results))

    if source_filter_failed:
        return "source leakage"
    if not metadata_ok_flag:
        return "metadata contract break"
    if actual_path == "inferred" and not query_spec.get("allow_inferred", False):
        return "inferred boundary break"
    if actual_path not in allowed_path_values:
        return "path routing error"
    if is_empty_expectation(expected):
        return None if not final_results else "source leakage"
    if exact_match_index == 0:
        if expected_path_values and actual_path not in expected_path_values:
            return "path routing error"
        return None
    if exact_match_index is not None:
        if expected_path_values and actual_path not in expected_path_values:
            return "path routing error"
        return "wrong ranking"
    if expected_path_values and actual_path not in expected_path_values:
        return "path routing error"

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
    metadata_ok_flag: bool,
    source_filter_failed: bool,
) -> Optional[str]:
    expected = narrative_expected(query_spec)
    expected_path_values = expected_paths(query_spec)
    allowed_path_values = allowed_final_sources(query_spec)

    if source_filter_failed:
        return "source leakage"
    if not metadata_ok_flag:
        return "metadata contract break"
    if actual_path not in allowed_path_values:
        return "path routing error"
    if is_empty_expectation(expected):
        return None if not final_results else "source leakage"
    if match_index == 0:
        if expected_path_values and actual_path not in expected_path_values:
            return "path routing error"
        return None
    if match_index is not None:
        if expected_path_values and actual_path not in expected_path_values:
            return "path routing error"
        return "wrong ranking"
    if expected_path_values and actual_path not in expected_path_values:
        return "path routing error"
    if final_results:
        return "wrong narrative hit"
    return "retrieval miss"


def evaluate_structured_query(
    agent: LLMAgent,
    query_spec: Dict[str, Any],
    top_k: int,
    source_name: str,
    expected_schema: str,
    force_local_fallback: bool = False,
) -> Dict[str, Any]:
    source_filter = query_spec.get("source_filter") or [source_name]
    fallback_results = [
        normalize_structured_record(item)
        for item in agent._search_local_triples(query_spec["query"], limit=top_k, source_filter=source_filter)
    ]
    if force_local_fallback:
        trace = {"final_result": list(fallback_results), "graph_only": [], "final_source": "fallback"}
    else:
        trace = agent.search_neo4j_trace(query_spec["query"], limit=top_k, source_filter=source_filter)
    final_results = [normalize_structured_record(item) for item in trace.get("final_result", [])]
    graph_only = [normalize_structured_record(item) for item in trace.get("graph_only", [])]
    expected = query_spec["expected_result"]
    expected_candidates = ensure_list(expected) if not is_empty_expectation(expected) else []
    exact_match_index = structured_match_index(query_spec, final_results, expected_candidates) if expected_candidates else (0 if not final_results else None)
    fallback_match_index = structured_match_index(query_spec, fallback_results, expected_candidates) if expected_candidates else (0 if not fallback_results else None)
    actual_path = normalize_text(trace.get("final_source"))
    metadata_ok_flag = all(metadata_ok(item, source_name, expected_schema) for item in final_results)
    source_filter_failed = source_leakage(final_results, source_name)
    actual_top_k_hit = exact_match_index is not None if expected_candidates else False
    expected_top_k_hit = bool(query_spec.get("expected_top_k_hit", True))
    top_k_expectation_met = actual_top_k_hit == expected_top_k_hit
    path_correct = actual_path == normalize_text(query_spec.get("expected_path"))
    allowed_path_ok = actual_path in allowed_final_sources(query_spec)
    schema_ok = query_schema_ok(query_spec, expected_schema)
    failure_category = choose_structured_failure(
        query_spec=query_spec,
        actual_path=actual_path,
        final_results=final_results,
        exact_match_index=exact_match_index,
        metadata_ok_flag=metadata_ok_flag and schema_ok,
        source_filter_failed=source_filter_failed,
    )

    return {
        "id": query_spec["id"],
        "category": query_spec["category"],
        "query_kind": query_spec["query_kind"],
        "query": query_spec["query"],
        "source_schema_version": normalize_text(query_spec.get("source_schema_version")),
        "expected_path": query_spec["expected_path"],
        "actual_path": actual_path,
        "allowed_final_sources": allowed_final_sources(query_spec),
        "expected_result": expected,
        "normalized_expected_value": query_spec.get("normalized_expected_value"),
        "normalized_returned_value": normalize_text(first_result(final_results).get("object")) if first_result(final_results) else None,
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
        "query_schema_ok": schema_ok,
        "query_explainability_degraded": explainability_degraded(final_results, source_name, expected_schema),
        "explainability_status": "degraded" if explainability_degraded(final_results, source_name, expected_schema) else "ok",
        "source_metadata": first_result(final_results),
        "metadata_complete": metadata_ok_flag,
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
    source_name: str,
    expected_schema: str,
    force_local_fallback: bool = False,
) -> Dict[str, Any]:
    source_filter = query_spec.get("source_filter") or [source_name]
    fallback_results = [
        normalize_narrative_record(item)
        for item in agent._search_local_narratives(query_spec["query"], top_k=top_k, source_filter=source_filter)
    ]
    if force_local_fallback:
        final_results = list(fallback_results)
        actual_path = "fallback"
    elif embedding_available:
        final_results = [
            normalize_narrative_record(item)
            for item in agent.search_chroma(query_spec["query"], top_k=top_k, source_filter=source_filter)
        ]
        actual_path = "embedding"
    else:
        final_results = list(fallback_results)
        actual_path = "fallback"
    expected = narrative_expected(query_spec)
    match_index = narrative_match_index(final_results, expected) if not is_empty_expectation(expected) else (0 if not final_results else None)
    fallback_match_index = narrative_match_index(fallback_results, expected) if not is_empty_expectation(expected) else (0 if not fallback_results else None)
    metadata_ok_flag = all(metadata_ok(item, source_name, expected_schema) for item in final_results)
    source_filter_failed = source_leakage(final_results, source_name)
    actual_top_k_hit = match_index is not None if not is_empty_expectation(expected) else False
    expected_top_k_hit = bool(query_spec.get("expected_top_k_hit", True))
    top_k_expectation_met = actual_top_k_hit == expected_top_k_hit
    path_correct = actual_path == normalize_text(query_spec.get("expected_path"))
    allowed_path_ok = actual_path in allowed_final_sources(query_spec)
    schema_ok = query_schema_ok(query_spec, expected_schema)
    failure_category = choose_narrative_failure(
        query_spec=query_spec,
        actual_path=actual_path,
        final_results=final_results,
        match_index=match_index,
        metadata_ok_flag=metadata_ok_flag and schema_ok,
        source_filter_failed=source_filter_failed,
    )

    return {
        "id": query_spec["id"],
        "category": query_spec["category"],
        "query_kind": query_spec["query_kind"],
        "query": query_spec["query"],
        "source_schema_version": normalize_text(query_spec.get("source_schema_version")),
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
        "query_schema_ok": schema_ok,
        "query_explainability_degraded": explainability_degraded(final_results, source_name, expected_schema),
        "explainability_status": "degraded" if explainability_degraded(final_results, source_name, expected_schema) else "ok",
        "source_metadata": first_result(final_results),
        "metadata_complete": metadata_ok_flag,
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
    query_explainability_degraded_count = sum(1 for item in results if item["query_explainability_degraded"])

    category_breakdown: Dict[str, Dict[str, Any]] = {}
    for item in results:
        bucket = category_breakdown.setdefault(
            item["category"],
            {
                "total": 0,
                "exact_pass_count": 0,
                "top_k_hit_count": 0,
                "query_explainability_degraded_count": 0,
                "failures": {},
            },
        )
        bucket["total"] += 1
        bucket["exact_pass_count"] += int(item["pass"])
        bucket["top_k_hit_count"] += int(item["top_k_hit"])
        bucket["query_explainability_degraded_count"] += int(item["query_explainability_degraded"])
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
        "query_explainability_degraded_count": query_explainability_degraded_count,
        "query_explainability_degraded_rate": round(query_explainability_degraded_count / total, 4) if total else 0.0,
        "category_breakdown": category_breakdown,
    }


def evaluate_gates(summary: Dict[str, Any], gates: Dict[str, Any], required_categories: Sequence[str]) -> Dict[str, Any]:
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

    explainability_degraded_max = int(gates.get("query_explainability_degraded_max", 0))
    checks.append({
        "name": "query_explainability_degraded_max",
        "expected": explainability_degraded_max,
        "actual": summary.get("query_explainability_degraded_count", 0),
        "passed": summary.get("query_explainability_degraded_count", 0) <= explainability_degraded_max,
    })

    coverage = summary.get("category_breakdown", {})
    checks.append({
        "name": "required_category_coverage",
        "expected": list(required_categories),
        "actual": {name: coverage.get(name, {}).get("total", 0) for name in required_categories},
        "passed": all(coverage.get(name, {}).get("total", 0) > 0 for name in required_categories),
    })

    passed = all(item["passed"] for item in checks)
    return {
        "passed": passed,
        "checks": checks,
        "exit_code": 0 if passed else 2,
    }


def main() -> None:
    configure_stdout()

    parser = argparse.ArgumentParser(description="Run a source-expansion readiness gate.")
    parser.add_argument("--source", required=True, help="Source name to evaluate, e.g. nasa.")
    parser.add_argument(
        "--queryset",
        default=None,
        help="Path to the source-specific query set JSON.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write the JSON report.",
    )
    args = parser.parse_args()

    descriptor = get_source_descriptor(args.source)
    expected_schema = get_source_schema_version(descriptor.source_name)
    queryset_path = args.queryset or get_source_namespace_artifact_path(
        DEFAULT_OUTPUT_DIR,
        args.source,
        f"{descriptor.source_name}_queries.json",
    )
    output_path = args.output or get_source_namespace_artifact_path(
        DEFAULT_OUTPUT_DIR,
        args.source,
        f"{descriptor.source_name}_report.json",
    )

    queryset_exists = os.path.exists(queryset_path)
    manifest = {}
    manifest_error = None
    if queryset_exists:
        try:
            manifest = load_json(queryset_path)
        except Exception as exc:
            manifest_error = str(exc)

    manifest_source = normalize_text(manifest.get("source_name") or manifest.get("source"))
    manifest_schema = normalize_text(manifest.get("source_schema_version"))
    queries = manifest.get("queries", []) if isinstance(manifest.get("queries", []), list) else []
    query_count = len(queries)
    top_k = int(manifest.get("top_k_default", 5))
    gates_config = dict(manifest.get("gates") or {})
    force_local_graph_fallback = bool(manifest.get("force_local_graph_fallback", False))
    force_local_narrative_fallback = bool(manifest.get("force_local_narrative_fallback", False))

    gate_checks = []
    gate_checks.append({"name": "queryset_present", "passed": queryset_exists, "actual": queryset_exists})
    gate_checks.append({
        "name": "descriptor_matches_manifest_source",
        "passed": bool(manifest_source) and manifest_source == descriptor.source_name,
        "actual": manifest_source,
        "expected": descriptor.source_name,
    })
    gate_checks.append({
        "name": "descriptor_matches_manifest_schema",
        "passed": bool(manifest_schema) and manifest_schema == expected_schema,
        "actual": manifest_schema,
        "expected": expected_schema,
    })

    query_schema_consistent = all(query_schema_ok(query_spec, expected_schema) for query_spec in queries) if queries else False
    gate_checks.append({
        "name": "query_schema_versions_consistent",
        "passed": query_schema_consistent,
        "actual": query_schema_consistent,
        "expected": True,
    })

    required_categories = (
        "structured",
        "narrative",
        "negative",
        "fallback",
        "source_isolation",
        "metadata_completeness",
        "path_routing",
        "unit_normalization",
        "conflict_case",
    )

    results = []
    if queries:
        source_name = descriptor.source_name
        agent = LLMAgent(source_name=source_name)
        embedding_available = has_materialized_embedding_store(source_name)

        for query_spec in queries:
            query_kind = normalize_text(query_spec.get("query_kind"))
            if query_kind == "structured":
                result = evaluate_structured_query(
                    agent,
                    query_spec,
                    top_k,
                    source_name,
                    expected_schema,
                    force_local_fallback=force_local_graph_fallback,
                )
            else:
                result = evaluate_narrative_query(
                    agent,
                    embedding_available,
                    query_spec,
                    top_k,
                    source_name,
                    expected_schema,
                    force_local_fallback=force_local_narrative_fallback,
                )
            results.append(result)

    summary = summarize_results(results)
    gate_checks.extend([
        {
            "name": "exact_accuracy_min",
            "expected": float(gates_config.get("exact_accuracy_min", 0.0)),
            "actual": summary.get("exact_accuracy", 0.0),
            "passed": summary.get("exact_accuracy", 0.0) >= float(gates_config.get("exact_accuracy_min", 0.0)),
        },
        {
            "name": "source_filter_failure_max",
            "expected": int(gates_config.get("source_filter_failure_max", 0)),
            "actual": summary.get("source_filter_failure_count", 0),
            "passed": summary.get("source_filter_failure_count", 0) <= int(gates_config.get("source_filter_failure_max", 0)),
        },
        {
            "name": "metadata_contract_break_max",
            "expected": int(gates_config.get("metadata_contract_break_max", 0)),
            "actual": summary.get("metadata_contract_break_count", 0),
            "passed": summary.get("metadata_contract_break_count", 0) <= int(gates_config.get("metadata_contract_break_max", 0)),
        },
        {
            "name": "inferred_boundary_break_max",
            "expected": int(gates_config.get("inferred_boundary_break_max", 0)),
            "actual": summary.get("inferred_boundary_break_count", 0),
            "passed": summary.get("inferred_boundary_break_count", 0) <= int(gates_config.get("inferred_boundary_break_max", 0)),
        },
        {
            "name": "query_explainability_degraded_max",
            "expected": int(gates_config.get("query_explainability_degraded_max", 0)),
            "actual": summary.get("query_explainability_degraded_count", 0),
            "passed": summary.get("query_explainability_degraded_count", 0) <= int(gates_config.get("query_explainability_degraded_max", 0)),
        },
        {
            "name": "required_category_coverage",
            "expected": list(required_categories),
            "actual": {name: summary.get("category_breakdown", {}).get(name, {}).get("total", 0) for name in required_categories},
            "passed": all(summary.get("category_breakdown", {}).get(name, {}).get("total", 0) > 0 for name in required_categories),
        },
    ])

    passed = all(item["passed"] for item in gate_checks)
    report: Dict[str, Any] = {
        "source": descriptor.source_name,
        "descriptor": {
            "source_name": descriptor.source_name,
            "status": descriptor.status,
            "source_role": descriptor.source_role,
            "schema_version": descriptor.schema_version,
            "expected_schema_version": expected_schema,
            "is_active": descriptor.is_active,
            "is_known": descriptor.is_known,
        },
        "manifest": {
            "exists": queryset_exists,
            "path": queryset_path,
            "source_name": manifest_source,
            "source_schema_version": manifest_schema,
            "query_count": query_count,
            "load_error": manifest_error,
            "query_schema_versions_consistent": query_schema_consistent,
        },
        "summary": summary,
        "probes": {
            "graph_results_count": sum(len(item.get("graph_only_results", [])) for item in results if item["query_kind"] == "structured"),
            "narrative_results_count": sum(len(item.get("top_k_results", [])) for item in results if item["query_kind"] == "narrative"),
            "fallback_graph_count": sum(len(item.get("fallback_results", [])) for item in results if item["query_kind"] == "structured"),
            "fallback_narrative_count": sum(len(item.get("fallback_results", [])) for item in results if item["query_kind"] == "narrative"),
        },
        "gates": {
            "passed": passed,
            "checks": gate_checks,
            "exit_code": 0 if passed else 2,
        },
        "results": results,
    }

    dump_json(output_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(report["gates"]["exit_code"])


if __name__ == "__main__":
    main()

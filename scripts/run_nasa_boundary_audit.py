import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import ACTIVE_SOURCE, ACTIVE_SOURCE_TEST, BASE_DIR
from src.agent.llm_agent import LLMAgent


DEFAULT_MANIFEST = os.path.join(
    BASE_DIR,
    "evaluation",
    "source_expansion",
    "nasa",
    "nasa_boundary_audit_manifest.json",
)
DEFAULT_REPORT = os.path.join(
    BASE_DIR,
    "evaluation",
    "source_expansion",
    "nasa",
    "nasa_boundary_audit_report.json",
)


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


def first_result(records: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return dict(records[0]) if records else None


def source_name(record: Optional[Dict[str, Any]]) -> str:
    if not record:
        return ""
    return normalize_text(record.get("source_name") or record.get("source"))


def is_metadata_complete(record: Optional[Dict[str, Any]]) -> bool:
    if not record:
        return True
    required_fields = ("source", "source_name", "source_role", "origin", "source_title", "schema_version")
    return all(normalize_text(record.get(field)) for field in required_fields)


def extract_percentage_claims(text: Any) -> List[str]:
    value = normalize_text(text)
    if not value:
        return []
    return sorted(set(re.findall(r"\d+(?:\.\d+)?\s*%", value)))


def compare_structured_records(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not left and not right:
        return {"same": True, "conflict_type": "none"}
    if not left or not right:
        return {"same": False, "conflict_type": "missing_on_one_side"}

    left_subject = normalize_text(left.get("subject"))
    left_relation = normalize_text(left.get("relation"))
    left_object = normalize_text(left.get("object"))
    right_subject = normalize_text(right.get("subject"))
    right_relation = normalize_text(right.get("relation"))
    right_object = normalize_text(right.get("object"))

    if left_subject != right_subject or left_relation != right_relation:
        return {
            "same": False,
            "conflict_type": "topic_mismatch",
        }
    if left_object != right_object:
        return {
            "same": False,
            "conflict_type": "structured_value_conflict",
        }
    return {"same": True, "conflict_type": "none"}


def compare_narrative_records(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not left and not right:
        return {"same": True, "conflict_type": "none"}
    if not left or not right:
        return {"same": False, "conflict_type": "missing_on_one_side"}

    left_title = normalize_text(left.get("page_title"))
    right_title = normalize_text(right.get("page_title"))
    left_section = normalize_text(left.get("section"))
    right_section = normalize_text(right.get("section"))
    left_claims = extract_percentage_claims(left.get("content") or left.get("raw") or "")
    right_claims = extract_percentage_claims(right.get("content") or right.get("raw") or "")

    if left_title != right_title or left_section != right_section:
        return {
            "same": False,
            "conflict_type": "topic_mismatch",
        }
    if left_claims != right_claims and (left_claims or right_claims):
        return {
            "same": False,
            "conflict_type": "numeric_claim_divergence",
        }
    if normalize_text(left.get("content")) != normalize_text(right.get("content")):
        return {
            "same": False,
            "conflict_type": "content_variation",
        }
    return {"same": True, "conflict_type": "none"}


def source_boundary_ok(records: Sequence[Dict[str, Any]], expected_source: str) -> bool:
    for record in records:
        actual = source_name(record)
        if actual and actual != expected_source:
            return False
    return True


def summarize_records(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "count": len(records),
        "top1": first_result(records),
        "metadata_complete": all(is_metadata_complete(item) for item in records),
        "source_boundary_ok": source_boundary_ok(records, normalize_text(source_name(first_result(records)))),
    }


def run_query(agent: LLMAgent, query: str, source_filter: Optional[List[str]] = None) -> Dict[str, Any]:
    graph_trace = agent.search_neo4j_trace(query, limit=5, source_filter=source_filter)
    narrative_results = agent.search_chroma(query, top_k=5, source_filter=source_filter)
    graph_results = [dict(item) for item in graph_trace.get("final_result", [])]
    narrative_results = [dict(item) for item in narrative_results]
    expected_source = normalize_text((source_filter or [ACTIVE_SOURCE])[0])

    graph_source_ok = source_boundary_ok(graph_results, expected_source)
    narrative_source_ok = source_boundary_ok(narrative_results, expected_source)
    graph_metadata_ok = all(is_metadata_complete(item) for item in graph_results)
    narrative_metadata_ok = all(is_metadata_complete(item) for item in narrative_results)

    return {
        "query": query,
        "expected_source": expected_source,
        "graph": {
            "final_source": graph_trace.get("final_source"),
            "source_filter_ok": graph_source_ok,
            "metadata_ok": graph_metadata_ok,
            "explainability_degraded": not graph_metadata_ok,
            "results": graph_results,
        },
        "narrative": {
            "source_filter_ok": narrative_source_ok,
            "metadata_ok": narrative_metadata_ok,
            "explainability_degraded": not narrative_metadata_ok,
            "results": narrative_results,
        },
        "pass": graph_source_ok and narrative_source_ok and graph_metadata_ok and narrative_metadata_ok,
    }


def run_controlled_activation(agent: LLMAgent, manifest: Dict[str, Any]) -> Dict[str, Any]:
    results = []
    for spec in manifest.get("controlled_activation_queries", []):
        query = normalize_text(spec.get("query"))
        nasa_probe = run_query(agent, query, source_filter=[ACTIVE_SOURCE_TEST])
        active_probe = run_query(LLMAgent(source_name=ACTIVE_SOURCE), query, source_filter=None)

        results.append({
            "id": normalize_text(spec.get("id")),
            "query": query,
            "nasa": nasa_probe,
            "active": active_probe,
            "cross_source_pollution": not nasa_probe["pass"] or not active_probe["pass"],
            "source_filter_failure": not nasa_probe["graph"]["source_filter_ok"] or not nasa_probe["narrative"]["source_filter_ok"],
            "query_explainability_degraded": nasa_probe["graph"]["explainability_degraded"] or nasa_probe["narrative"]["explainability_degraded"],
        })

    return {
        "total_queries": len(results),
        "source_filter_failure_count": sum(1 for item in results if item["source_filter_failure"]),
        "cross_source_pollution_count": sum(1 for item in results if item["cross_source_pollution"]),
        "query_explainability_degraded_count": sum(1 for item in results if item["query_explainability_degraded"]),
        "results": results,
    }


def run_conflict_probes(agent: LLMAgent, manifest: Dict[str, Any]) -> Dict[str, Any]:
    results = []
    active_agent = LLMAgent(source_name=ACTIVE_SOURCE)
    for spec in manifest.get("conflict_probes", []):
        query = normalize_text(spec.get("query"))
        mode = normalize_text(spec.get("mode"))
        nasa_graph = agent.search_neo4j_trace(query, limit=5, source_filter=[ACTIVE_SOURCE_TEST])
        active_graph = active_agent.search_neo4j_trace(query, limit=5)
        nasa_narrative = agent.search_chroma(query, top_k=5, source_filter=[ACTIVE_SOURCE_TEST])
        active_narrative = active_agent.search_chroma(query, top_k=5)

        nasa_graph_top1 = first_result(nasa_graph.get("final_result", []))
        active_graph_top1 = first_result(active_graph.get("final_result", []))
        nasa_narrative_top1 = first_result(nasa_narrative)
        active_narrative_top1 = first_result(active_narrative)

        graph_comparison = compare_structured_records(nasa_graph_top1, active_graph_top1)
        narrative_comparison = compare_narrative_records(nasa_narrative_top1, active_narrative_top1)

        results.append({
            "id": normalize_text(spec.get("id")),
            "entity": normalize_text(spec.get("entity")),
            "query": query,
            "mode": mode,
            "graph": {
                "nasa": {
                    "final_source": nasa_graph.get("final_source"),
                    "top1": nasa_graph_top1,
                },
                "active": {
                    "final_source": active_graph.get("final_source"),
                    "top1": active_graph_top1,
                },
                "comparison": graph_comparison,
            },
            "narrative": {
                "nasa": {
                    "top1": nasa_narrative_top1,
                },
                "active": {
                    "top1": active_narrative_top1,
                },
                "comparison": narrative_comparison,
            },
            "source_boundary_ok": source_boundary_ok(nasa_graph.get("final_result", []), ACTIVE_SOURCE_TEST)
            and source_boundary_ok(active_graph.get("final_result", []), ACTIVE_SOURCE),
            "conflict_observed": (not graph_comparison["same"]) or (not narrative_comparison["same"]),
        })

    return {
        "total_probes": len(results),
        "conflict_observed_count": sum(1 for item in results if item["conflict_observed"]),
        "source_boundary_failure_count": sum(1 for item in results if not item["source_boundary_ok"]),
        "results": results,
    }


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Run the NASA controlled activation and cross-source conflict audit.")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Path to the audit manifest JSON.")
    parser.add_argument("--output", default=DEFAULT_REPORT, help="Path to write the audit report JSON.")
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    active_source = normalize_text(manifest.get("active_source") or ACTIVE_SOURCE)
    active_source_test = normalize_text(manifest.get("active_source_test") or ACTIVE_SOURCE_TEST)
    if active_source != ACTIVE_SOURCE:
        raise RuntimeError(f"Manifest active_source must be '{ACTIVE_SOURCE}', got '{active_source}'")
    if active_source_test != ACTIVE_SOURCE_TEST:
        raise RuntimeError(f"Manifest active_source_test must be '{ACTIVE_SOURCE_TEST}', got '{active_source_test}'")

    nasa_agent = LLMAgent(source_name=ACTIVE_SOURCE_TEST)
    controlled_activation = run_controlled_activation(nasa_agent, manifest)
    conflict_probes = run_conflict_probes(nasa_agent, manifest)

    report = {
        "manifest_path": args.manifest,
        "active_source": ACTIVE_SOURCE,
        "active_source_test": ACTIVE_SOURCE_TEST,
        "controlled_activation": controlled_activation,
        "cross_source_conflicts": conflict_probes,
        "boundary_pass": (
            controlled_activation["source_filter_failure_count"] == 0
            and controlled_activation["cross_source_pollution_count"] == 0
            and controlled_activation["query_explainability_degraded_count"] == 0
            and conflict_probes["source_boundary_failure_count"] == 0
        ),
    }
    report["gates"] = {
        "passed": report["boundary_pass"],
        "checks": [
            {
                "name": "source_filter_failure_count",
                "actual": controlled_activation["source_filter_failure_count"],
                "passed": controlled_activation["source_filter_failure_count"] == 0,
            },
            {
                "name": "cross_source_pollution_count",
                "actual": controlled_activation["cross_source_pollution_count"],
                "passed": controlled_activation["cross_source_pollution_count"] == 0,
            },
            {
                "name": "query_explainability_degraded_count",
                "actual": controlled_activation["query_explainability_degraded_count"],
                "passed": controlled_activation["query_explainability_degraded_count"] == 0,
            },
            {
                "name": "conflict_source_boundary_failure_count",
                "actual": conflict_probes["source_boundary_failure_count"],
                "passed": conflict_probes["source_boundary_failure_count"] == 0,
            },
        ],
        "exit_code": 0 if report["boundary_pass"] else 2,
    }

    dump_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(report["gates"]["exit_code"])


if __name__ == "__main__":
    main()

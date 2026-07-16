import glob
import json
import os
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import ACTIVE_SOURCE, RAW_JSON_DIR, TRIPLES_DIR
from src.agent.llm_agent import LLMAgent
from src.knowledge_graph.neo4j_loader import Neo4jLoader
from src.nlp.ontology import ALLOWED_RELATIONS
from src.nlp.text_normalizer import normalize_narrative_record, normalize_triple_record
from src.source_control import SOURCE_ROLE, SOURCE_SCHEMA_VERSION
from src.vector_store.chroma_store import ChromaStore


STRUCTURED_SMOKE_PROBES = [
    {
        "category": "ORBITS",
        "query": "月球绕谁公转",
        "expected_path": "graph",
        "expected": {"subject": "月球", "relation": "ORBITS", "object": "地球"},
    },
    {
        "category": "PART_OF",
        "query": "木卫一属于什么系统",
        "expected_path": "graph",
        "expected": {"subject": "木卫一", "relation": "PART_OF", "object": "木星系统"},
    },
    {
        "category": "LOCATED_IN",
        "query": "海王星在哪里",
        "expected_path": "graph",
        "expected": {"subject": "海王星", "relation": "LOCATED_IN", "object": "太阳系"},
    },
    {
        "category": "HAS_RADIUS",
        "query": "太阳半径是多少",
        "expected_path": "graph",
        "expected": {"subject": "太阳", "relation": "HAS_RADIUS", "object": "695,000 km"},
    },
    {
        "category": "HAS_ATMOSPHERE",
        "query": "火星大气成分",
        "expected_path": "graph",
        "expected_objects": ["CO2", "N2", "Ar", "O2"],
    },
    {
        "category": "DISCOVERED_BY",
        "query": "谁发现了冥王星",
        "expected_path": "graph",
        "expected": {"subject": "冥王星", "relation": "DISCOVERED_BY", "object": "克莱德·汤博"},
    },
]

NARRATIVE_SMOKE_PROBES = [
    {
        "category": "narrative explanation",
        "query": "为什么火星大气稀薄",
        "expected_page_title": "火星",
    },
]

SOURCE_BOUNDARY_CHECKS = [
    {
        "name": "graph_default_filter",
        "query": "火卫一绕谁公转",
        "kind": "graph",
        "source_filter": None,
        "expect_non_empty": True,
    },
    {
        "name": "graph_negative_filter",
        "query": "火卫一绕谁公转",
        "kind": "graph",
        "source_filter": ["nasa"],
        "expect_non_empty": False,
    },
    {
        "name": "embedding_default_filter",
        "query": "火星大气成分",
        "kind": "embedding",
        "source_filter": None,
        "expect_non_empty": True,
    },
    {
        "name": "embedding_negative_filter",
        "query": "火星大气成分",
        "kind": "embedding",
        "source_filter": ["nasa"],
        "expect_non_empty": False,
    },
]


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_quantity(value: Any) -> str:
    return _normalize_text(value).replace("×", "x").replace(" ", "").replace(",", "").replace("，", "").lower()


def _brief_structured(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "subject": item.get("subject"),
            "relation": item.get("relation"),
            "object": item.get("object"),
            "source_name": item.get("source_name") or item.get("source"),
            "source_role": item.get("source_role"),
        }
        for item in records
    ]


def _brief_narrative(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "page_title": item.get("page_title"),
            "section": item.get("section"),
            "rank": item.get("rank"),
            "source_name": item.get("source_name") or item.get("source"),
            "source_role": item.get("source_role"),
        }
        for item in records
    ]


def _match_structured_result(records: List[Dict[str, Any]], expected: Dict[str, str]) -> bool:
    for item in records:
        if (
            _normalize_text(item.get("subject")) == expected["subject"]
            and _normalize_text(item.get("relation")) == expected["relation"]
        ):
            expected_object = expected["object"]
            if expected["relation"] in {"HAS_RADIUS", "HAS_MASS"}:
                if _normalize_quantity(item.get("object")) == _normalize_quantity(expected_object):
                    return True
            elif _normalize_text(item.get("object")) == expected_object:
                return True
    return False


def _source_contract_ok(records: List[Dict[str, Any]]) -> bool:
    for item in records:
        if _normalize_text(item.get("source_name") or item.get("source")) != ACTIVE_SOURCE:
            return False
        if _normalize_text(item.get("source_role")) != SOURCE_ROLE:
            return False
    return True


def collect_local_stats() -> Dict[str, Any]:
    triple_files = sorted(glob.glob(os.path.join(TRIPLES_DIR, "*_triples.json")))
    narrative_files = sorted(glob.glob(os.path.join(TRIPLES_DIR, "*_narratives.json")))
    raw_files = sorted(glob.glob(os.path.join(RAW_JSON_DIR, "*.json")))

    raw_bad_source = 0
    raw_missing_source_role = 0
    raw_missing_origin = 0
    raw_missing_fetch_source = 0
    for path in raw_files:
        try:
            record = _load_json(path)
        except Exception:
            continue
        if not isinstance(record, dict):
            continue
        if record.get("source") != ACTIVE_SOURCE:
            raw_bad_source += 1
        if record.get("source_role") != SOURCE_ROLE:
            raw_missing_source_role += 1
        if not record.get("origin"):
            raw_missing_origin += 1
        if not record.get("fetch_source"):
            raw_missing_fetch_source += 1

    triple_records = []
    narrative_records = []
    for path in triple_files:
        try:
            triple_records.extend(normalize_triple_record(item) for item in _load_json(path))
        except Exception:
            continue
    for path in narrative_files:
        try:
            narrative_records.extend(normalize_narrative_record(item) for item in _load_json(path))
        except Exception:
            continue

    graph_bad_relation_types = sum(
        1 for item in triple_records if item.get("relation") not in ALLOWED_RELATIONS
    )
    triple_bad_metadata = sum(
        1
        for item in triple_records
        if item.get("source") != ACTIVE_SOURCE
        or item.get("source_role") != SOURCE_ROLE
        or not item.get("origin")
    )
    narrative_bad_metadata = sum(
        1
        for item in narrative_records
        if item.get("source") != ACTIVE_SOURCE
        or item.get("source_role") != SOURCE_ROLE
        or not item.get("origin")
    )

    return {
        "active_source": ACTIVE_SOURCE,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "raw_json_count": len(raw_files),
        "triples_file_count": len(triple_files),
        "triples_record_count": len(triple_records),
        "narratives_file_count": len(narrative_files),
        "narratives_record_count": len(narrative_records),
        "raw_bad_source_count": raw_bad_source,
        "raw_missing_source_role_count": raw_missing_source_role,
        "raw_missing_origin_count": raw_missing_origin,
        "raw_missing_fetch_source_count": raw_missing_fetch_source,
        "graph_bad_relation_types_count": graph_bad_relation_types,
        "local_triple_bad_metadata_count": triple_bad_metadata,
        "local_narrative_bad_metadata_count": narrative_bad_metadata,
    }


def collect_summary() -> Dict[str, Any]:
    summary_path = os.path.join(TRIPLES_DIR, "summary.json")
    if not os.path.exists(summary_path):
        return {"exists": False}
    payload = _load_json(summary_path)
    payload["exists"] = True
    return payload


def collect_neo4j() -> Dict[str, Any]:
    loader = Neo4jLoader()
    result = {"available": bool(loader.driver)}
    if not loader.driver:
        return result

    allowed = sorted(loader.GRAPH_RELATION_WHITELIST)
    with loader.driver.session() as session:
        result["relationship_count"] = session.run(
            "MATCH ()-[r]->() RETURN count(r) AS c"
        ).single()["c"]
        result["graph_bad_relation_types_count"] = session.run(
            "MATCH ()-[r]->() WHERE NOT type(r) IN $allowed RETURN count(r) AS c",
            allowed=allowed,
        ).single()["c"]
        result["graph_bad_metadata_count"] = session.run(
            "MATCH ()-[r]->() "
            "WHERE coalesce(r.source, '') <> $active_source "
            "OR coalesce(r.source_role, '') <> $source_role "
            "OR coalesce(r.origin, '') = '' "
            "RETURN count(r) AS c",
            active_source=ACTIVE_SOURCE,
            source_role=SOURCE_ROLE,
        ).single()["c"]
    loader.close()
    return result


def collect_chroma() -> Dict[str, Any]:
    stats = ChromaStore().get_stats()
    return {
        "total_count": stats.get("total", 0),
        "collections": stats.get("collections", []),
    }


def collect_live_path_probes() -> Dict[str, Any]:
    agent = LLMAgent()
    structured_results = []
    narrative_results = []

    for spec in STRUCTURED_SMOKE_PROBES:
        trace = agent.search_neo4j_trace(spec["query"], limit=5)
        final_results = trace.get("final_result", [])
        smoke_pass = False
        if "expected" in spec:
            smoke_pass = _match_structured_result(final_results, spec["expected"])
        else:
            actual_objects = {_normalize_text(item.get("object")) for item in final_results}
            smoke_pass = set(spec["expected_objects"]).issubset(actual_objects)

        smoke_pass = smoke_pass and trace.get("final_source") == spec["expected_path"]
        smoke_pass = smoke_pass and _source_contract_ok(final_results)

        structured_results.append({
            "category": spec["category"],
            "query": spec["query"],
            "expected_path": spec["expected_path"],
            "actual_path": trace.get("final_source"),
            "result_count": len(final_results),
            "smoke_pass": smoke_pass,
            "top_results": _brief_structured(final_results[:5]),
        })

    for spec in NARRATIVE_SMOKE_PROBES:
        results = agent.search_chroma(spec["query"], top_k=5)
        top_title = _normalize_text(results[0].get("page_title")) if results else ""
        smoke_pass = bool(results) and top_title == spec["expected_page_title"] and _source_contract_ok(results)
        narrative_results.append({
            "category": spec["category"],
            "query": spec["query"],
            "expected_page_title": spec["expected_page_title"],
            "result_count": len(results),
            "smoke_pass": smoke_pass,
            "top_results": _brief_narrative(results[:5]),
        })

    all_pass = all(item["smoke_pass"] for item in structured_results + narrative_results)
    return {
        "validation_level": "smoke",
        "note": "These probes cover representative query categories only. They are broader than the old two-question check, but they are still not full retrieval certification.",
        "structured": structured_results,
        "narrative": narrative_results,
        "status": {
            "all_smoke_probes_pass": all_pass,
            "covered_categories": [
                "ORBITS",
                "PART_OF",
                "LOCATED_IN",
                "HAS_RADIUS",
                "HAS_ATMOSPHERE",
                "DISCOVERED_BY",
                "narrative explanation",
            ],
        },
    }


def collect_source_boundary_checks() -> Dict[str, Any]:
    agent = LLMAgent()
    checks = []
    for spec in SOURCE_BOUNDARY_CHECKS:
        if spec["kind"] == "graph":
            trace = agent.search_neo4j_trace(spec["query"], limit=5, source_filter=spec["source_filter"])
            results = trace.get("final_result", [])
            actual_path = trace.get("final_source")
            source_contract_ok = _source_contract_ok(results)
            count = len(results)
        else:
            results = agent.search_chroma(spec["query"], top_k=5, source_filter=spec["source_filter"])
            actual_path = "embedding"
            source_contract_ok = _source_contract_ok(results)
            count = len(results)

        smoke_pass = (count > 0) if spec["expect_non_empty"] else (count == 0)
        smoke_pass = smoke_pass and source_contract_ok
        checks.append({
            "name": spec["name"],
            "kind": spec["kind"],
            "query": spec["query"],
            "source_filter": spec["source_filter"] or [ACTIVE_SOURCE],
            "expected_non_empty": spec["expect_non_empty"],
            "actual_path": actual_path,
            "result_count": count,
            "smoke_pass": smoke_pass,
        })

    return {
        "validation_level": "smoke",
        "checks": checks,
        "status": {
            "all_boundary_checks_pass": all(item["smoke_pass"] for item in checks),
        },
    }


def collect_known_issues() -> Dict[str, Any]:
    agent = LLMAgent()
    trace = agent.search_neo4j_trace("谁发现了谷神星", limit=5)
    fallback = agent._search_local_triples("谁发现了谷神星", limit=5)
    graph_top1 = trace.get("final_result", [None])[0] if trace.get("final_result") else None
    fallback_top1 = fallback[0] if fallback else None
    issue_open = bool(graph_top1 and fallback_top1) and (
        _normalize_text(graph_top1.get("subject")) != _normalize_text(fallback_top1.get("subject"))
        or _normalize_text(graph_top1.get("relation")) != _normalize_text(fallback_top1.get("relation"))
        or _normalize_text(graph_top1.get("object")) != _normalize_text(fallback_top1.get("object"))
    )

    return {
        "discover_ceres_graph": {
            "status": "open" if issue_open else "resolved",
            "blocking": False,
            "scope": "consistency_tail_only",
            "query": "谁发现了谷神星",
            "graph_top1": graph_top1,
            "fallback_top1": fallback_top1,
            "note": (
                "Known issue remains visible and non-blocking."
                if issue_open
                else "The previous DISCOVERED_BY graph/fallback top-1 inconsistency is not reproduced in this audit run."
            ),
        }
    }


def main() -> None:
    _configure_stdout()
    local_stats = collect_local_stats()
    summary = collect_summary()
    neo4j = collect_neo4j()
    chroma = collect_chroma()
    live_probes = collect_live_path_probes()
    source_boundary_checks = collect_source_boundary_checks()
    known_issues = collect_known_issues()

    local_checks_pass = (
        local_stats["raw_bad_source_count"] == 0
        and local_stats["raw_missing_source_role_count"] == 0
        and local_stats["raw_missing_origin_count"] == 0
        and local_stats["graph_bad_relation_types_count"] == 0
        and local_stats["local_triple_bad_metadata_count"] == 0
        and local_stats["local_narrative_bad_metadata_count"] == 0
    )

    source_isolation_validation = {
        "status": (
            "PASS"
            if local_checks_pass
            and live_probes["status"]["all_smoke_probes_pass"]
            and source_boundary_checks["status"]["all_boundary_checks_pass"]
            else "FAIL"
        ),
        "validation_level": "smoke",
        "note": "PASS here means artifact checks plus representative live probes passed. It should not be interpreted as exhaustive query-level certification.",
    }

    payload = {
        "local_metadata_and_persistent_artifact_checks": {
            "baseline": local_stats,
            "summary_artifact": summary,
            "neo4j": neo4j,
            "chroma": chroma,
            "status": {
                "local_checks_pass": local_checks_pass,
            },
        },
        "live_path_probes": live_probes,
        "source_boundary_checks": source_boundary_checks,
        "known_issues": known_issues,
        "source_isolation_validation": source_isolation_validation,
        "regression_entrypoints": {
            "baseline_audit": "python scripts/audit_single_source_baseline.py",
            "active_path_validation": "python scripts/verify_active_path.py",
            "retrieval_eval_gate": "python scripts/run_single_source_retrieval_eval.py",
            "pipeline_rebuild": "python -c \"from src.nlp.nlp_pipeline import NlpPipeline; print(NlpPipeline().process_all())\"",
            "single_source_converge": "python scripts/p5_converge_single_source.py",
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

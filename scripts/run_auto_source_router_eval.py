import json
import sys
from datetime import datetime
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.llm_agent import LLMAgent
from src.gui.main_window import AgentTab
from src.source_router import SourceRouter


REPORT_PATH = ROOT / "evaluation" / "auto_source_router_report.json"


QUERY_SPECS = [
    {"query": "火星质量是多少", "expected_sources": ["nasa", "wikidata", "zh_wikipedia", "esa"], "expected_authority_source": "nasa", "case": "numeric"},
    {"query": "地球平均半径是多少", "expected_sources": ["nasa", "wikidata", "zh_wikipedia", "esa"], "expected_authority_source": "nasa", "case": "numeric"},
    {"query": "金星大气成分是什么", "expected_sources": ["nasa", "wikidata", "zh_wikipedia", "esa"], "expected_authority_source": "nasa", "case": "numeric"},
    {"query": "月球绕行什么", "expected_sources": ["wikidata", "nasa", "zh_wikipedia", "esa"], "expected_authority_source": "wikidata", "case": "structured"},
    {"query": "木卫二属于什么系统", "expected_sources": ["wikidata", "nasa", "zh_wikipedia", "esa"], "expected_authority_source": "wikidata", "case": "structured"},
    {"query": "冥王星位于哪里", "expected_sources": ["wikidata", "nasa", "zh_wikipedia", "esa"], "expected_authority_source": "wikidata", "case": "structured"},
    {"query": "JUICE 探测任务研究什么", "expected_sources": ["esa", "nasa", "wikidata", "zh_wikipedia"], "expected_authority_source": "esa", "case": "esa"},
    {"query": "Rosetta 探测器做了什么", "expected_sources": ["esa", "nasa", "wikidata", "zh_wikipedia"], "expected_authority_source": "esa", "case": "esa"},
    {"query": "太阳为什么会发光", "expected_sources": ["zh_wikipedia", "nasa", "esa", "wikidata"], "expected_authority_source": "zh_wikipedia", "case": "narrative"},
    {"query": "月球的形成历史是什么", "expected_sources": ["zh_wikipedia", "nasa", "esa", "wikidata"], "expected_authority_source": "zh_wikipedia", "case": "narrative"},
    {"query": "火星质量是多少，为什么和地球不同", "expected_sources": ["nasa", "wikidata", "zh_wikipedia", "esa"], "expected_authority_source": "nasa", "case": "ambiguous"},
    {"query": "火星半径是多少，不同来源为什么不一样", "expected_sources": ["nasa", "wikidata", "zh_wikipedia", "esa"], "expected_authority_source": "nasa", "case": "conflict"},
]


def build_graph_record(source_name: str, subject: str, relation: str, obj: str) -> dict:
    return {
        "subject": subject,
        "relation": relation,
        "object": obj,
        "source": source_name,
        "source_name": source_name,
    }


def build_narrative_record(source_name: str, title: str, content: str) -> dict:
    return {
        "content": content,
        "page_title": title,
        "section": "概述",
        "source": source_name,
        "source_name": source_name,
    }


def build_fixture(spec: dict, selected_sources: list[str]) -> tuple[dict, dict]:
    neo4j_by_source = {source_name: [] for source_name in selected_sources}
    chroma_by_source = {source_name: [] for source_name in selected_sources}
    case = spec["case"]

    if case == "numeric":
        for source_name in selected_sources:
            neo4j_by_source[source_name] = [build_graph_record(source_name, "火星", "HAS_MASS", "6.4171e23 kg")]
            chroma_by_source[source_name] = [build_narrative_record(source_name, "火星", f"{source_name} 提供火星质量说明。")]
    elif case == "structured":
        neo4j_by_source["wikidata"] = [build_graph_record("wikidata", "月球", "ORBITS", "地球")]
    elif case == "esa":
        chroma_by_source["esa"] = [build_narrative_record("esa", "JUICE", "JUICE 任务聚焦木星系统与冰卫星。")]
    elif case == "narrative":
        chroma_by_source["zh_wikipedia"] = [build_narrative_record("zh_wikipedia", "太阳", "太阳发光与核心聚变有关。")]
    elif case == "ambiguous":
        neo4j_by_source["nasa"] = [build_graph_record("nasa", "火星", "HAS_MASS", "6.4171e23 kg")]
        neo4j_by_source["wikidata"] = [build_graph_record("wikidata", "火星", "HAS_MASS", "6.4171e23 kg")]
        chroma_by_source["zh_wikipedia"] = [build_narrative_record("zh_wikipedia", "火星", "火星质量较小与形成历史有关。")]
    elif case == "conflict":
        neo4j_by_source["nasa"] = [build_graph_record("nasa", "火星", "HAS_RADIUS", "3389.5 km")]
        neo4j_by_source["wikidata"] = [build_graph_record("wikidata", "火星", "HAS_RADIUS", "3396.2 km")]
        chroma_by_source["zh_wikipedia"] = [build_narrative_record("zh_wikipedia", "火星", "不同资料有不同写法。")]

    return neo4j_by_source, chroma_by_source


def evaluate() -> dict:
    router = SourceRouter()
    agent = LLMAgent(source_name="auto")
    cases = []
    passed_count = 0
    source_trace_missing_count = 0
    authority_mismatch_count = 0
    silent_conflict_count = 0

    for spec in QUERY_SPECS:
        routing_trace = router.route(spec["query"])
        selected_sources = list(routing_trace.get("selected_sources", []))
        expected_sources = spec["expected_sources"]
        route_ok = selected_sources == expected_sources
        if route_ok:
            passed_count += 1

        neo4j_by_source, chroma_by_source = build_fixture(spec, selected_sources)
        fused = agent._fuse_auto_results(
            spec["query"],
            neo4j_by_source=neo4j_by_source,
            chroma_by_source=chroma_by_source,
            routing_trace=routing_trace,
        )
        metadata = fused["metadata"]
        if not metadata.get("source_trace") or len(metadata["source_trace"]) != len(selected_sources):
            source_trace_missing_count += 1
        if metadata.get("authority_source") != spec["expected_authority_source"]:
            authority_mismatch_count += 1
        if spec["case"] == "conflict" and (
            not metadata.get("conflict_detected") or "来源存在差异" not in fused["answer_prompt"]
        ):
            silent_conflict_count += 1

        cases.append({
            "query": spec["query"],
            "case": spec["case"],
            "expected_sources": expected_sources,
            "selected_sources": selected_sources,
            "route_ok": route_ok,
            "routing_reason": routing_trace.get("routing_reason"),
            "fusion_mode": metadata.get("fusion_mode"),
            "authority_source": metadata.get("authority_source"),
            "source_trace": metadata.get("source_trace"),
            "conflict_detected": metadata.get("conflict_detected"),
        })

    router_accuracy = round(passed_count / len(QUERY_SPECS), 4)
    default_auto_enabled = (
        AgentTab.DEFAULT_SOURCE_NAME == "auto"
        and AgentTab.SOURCE_OPTIONS[0] == "auto"
        and AgentTab.SOURCE_LABELS.get("auto") == "自动（推荐）"
    )
    passed = (
        router_accuracy >= 0.80
        and source_trace_missing_count == 0
        and authority_mismatch_count == 0
        and silent_conflict_count == 0
        and default_auto_enabled
    )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total_queries": len(QUERY_SPECS),
            "route_pass_count": passed_count,
            "router_accuracy": router_accuracy,
            "source_trace_missing_count": source_trace_missing_count,
            "authority_mismatch_count": authority_mismatch_count,
            "silent_conflict_count": silent_conflict_count,
            "default_auto_enabled": default_auto_enabled,
        },
        "cases": cases,
        "gates": {
            "router_accuracy": router_accuracy,
            "source_trace_missing_count": source_trace_missing_count,
            "authority_mismatch_count": authority_mismatch_count,
            "silent_conflict_count": silent_conflict_count,
            "default_auto_enabled": default_auto_enabled,
            "passed": passed,
        },
    }


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = evaluate()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["gates"]["passed"], "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))
    return 0 if report["gates"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.agent.llm_agent import LLMAgent
from src.crawler.spider import TololoCrawler
from src.knowledge_graph.neo4j_loader import Neo4jLoader


CHROMA_QUERIES = [
    "为什么火星大气稀薄",
    "火星大气成分",
]

GRAPH_QUERIES = [
    "月球绕谁公转",
    "火卫一绕谁公转",
    "谁发现了冥王星",
    "海王星在哪里",
    "木卫一属于什么系统",
    "太阳有多大",
]

GRAPH_TRACE_QUERIES = [
    "海王星在哪里",
    "火卫一绕谁公转",
    "木卫一属于什么系统",
]

DIRTY_TERMS = [
    "与海王星的卫星相同，分别",
    "由前几代恒星",
    "四部分",
    "关于海王星外行星",
]


def brief_chroma(results):
    return [
        {
            "rank": item.get("rank"),
            "page_title": item.get("page_title"),
            "section": item.get("section"),
            "score": round(float(item.get("score", 0.0)), 4),
        }
        for item in results
    ]


def brief_graph(results):
    return [
        {
            "subject": item.get("subject"),
            "relation": item.get("relation"),
            "object": item.get("object"),
        }
        for item in results
    ]


def summarize_prompt(prompt):
    graph_results = []
    semantic_titles = []
    mode = None
    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped == "=== 知识图谱关系检索结果 ===":
            mode = "graph"
            continue
        if stripped == "=== 语义检索结果 ===":
            mode = "semantic"
            continue
        if not stripped:
            mode = None
            continue
        if mode == "graph" and stripped.startswith("- "):
            graph_results.append(stripped[2:])
        if mode == "semantic" and stripped.startswith("["):
            title = stripped.split("]", 1)[0].lstrip("[")
            semantic_titles.append(title)
    return {
        "graph_count": len(graph_results),
        "graph_results": graph_results,
        "semantic_count": len(semantic_titles),
        "semantic_titles": semantic_titles,
    }


def write_json_utf8(payload):
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.flush()
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    except (AttributeError, OSError, ValueError):
        pass
    sys.stdout.write(text)
    sys.stdout.write("\n")
    sys.stdout.flush()


def main():
    agent = LLMAgent()
    chroma_results = {query: brief_chroma(agent.search_chroma(query, top_k=5)) for query in CHROMA_QUERIES}
    graph_results = {query: brief_graph(agent.search_neo4j(query, limit=5)) for query in GRAPH_QUERIES}
    graph_trace = {}
    for query in GRAPH_TRACE_QUERIES:
        trace = agent.search_neo4j_trace(query, limit=5)
        graph_trace[query] = {
            "graph_only": brief_graph(trace.get("graph_only", [])),
            "final_result": brief_graph(trace.get("final_result", [])),
            "final_source": trace.get("final_source"),
        }
    loader = agent._get_neo4j_loader()
    dirty_counts = {}
    if loader and loader.driver:
        with loader.driver.session() as session:
            for term in DIRTY_TERMS:
                dirty_counts[term] = session.run(
                    "MATCH (n)-[r]->(m) WHERE n.name = $term OR m.name = $term RETURN count(r) AS c",
                    term=term,
                ).single()["c"]

    prompt = agent._build_system_prompt(
        agent.search_neo4j("火卫一绕谁公转", limit=5),
        agent.search_chroma("为什么火星大气稀薄", top_k=5),
    )

    crawler = TololoCrawler()
    page = crawler.get_page_content("火星") or {}

    payload = {
        "chroma": chroma_results,
        "graph": graph_results,
        "graph_trace": graph_trace,
        "inferred_count": sum(1 for item in graph_trace.values() if item.get("final_source") == "inferred"),
        "prompt_summary": summarize_prompt(prompt),
        "dirty_terms": dirty_counts,
        "crawler": {
            "attempted_api": crawler.last_attempted_api,
            "attempted_html_fallback": crawler.last_attempted_html_fallback,
            "final_fetch_status": crawler.last_fetch_status,
            "final_source": crawler.last_fetch_source,
            "source_for_mars": page.get("source"),
            "failure_reason": crawler.last_fetch_error,
            "attempt_errors": crawler.last_fetch_attempt_errors,
        },
    }
    write_json_utf8(payload)


if __name__ == "__main__":
    main()

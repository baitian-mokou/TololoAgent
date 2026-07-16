import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


REPORT_SPECS = [
    {
        "report_name": "single_source_retrieval",
        "source": "zh_wikipedia",
        "path": os.path.join(ROOT, "evaluation", "single_source_retrieval_report.json"),
    },
    {
        "report_name": "wikidata_source_expansion",
        "source": "wikidata",
        "path": os.path.join(ROOT, "evaluation", "source_expansion", "wikidata", "wikidata_report.json"),
    },
    {
        "report_name": "nasa_source_expansion",
        "source": "nasa",
        "path": os.path.join(ROOT, "evaluation", "source_expansion", "nasa", "nasa_report.json"),
    },
]

TRIAGE_JSON = os.path.join(ROOT, "evaluation", "eval_failure_triage.json")
TRIAGE_MD = os.path.join(ROOT, "docs", "retrieval_failure_triage.md")
BACKLOG_MD = os.path.join(ROOT, "docs", "retrieval_repair_backlog.md")

NEGATIVE_FALSE_FLAGS = (
    "pass",
    "exact_match",
    "top_k_expectation_met",
    "path_correct",
    "metadata_complete",
)
POSITIVE_TRUE_FLAGS = (
    "source_filter_failed",
    "inferred_boundary_break",
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


def write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def compact(value: Any, limit: int = 220) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def source_metadata_from_result(result: Dict[str, Any]) -> Dict[str, Any]:
    explicit = result.get("source_metadata")
    if isinstance(explicit, dict):
        return explicit
    returned = result.get("returned_result")
    if not isinstance(returned, dict):
        return {}
    keys = ("source", "source_name", "source_role", "origin", "schema_version", "source_title")
    return {key: returned.get(key) for key in keys if key in returned}


def triggered_failure_flags(result: Dict[str, Any]) -> List[str]:
    flags = []
    for field in NEGATIVE_FALSE_FLAGS:
        if field in result and result.get(field) is False:
            flags.append(f"{field}=false")
    for field in POSITIVE_TRUE_FLAGS:
        if result.get(field) is True:
            flags.append(f"{field}=true")
    return flags


def is_failure_result(result: Dict[str, Any]) -> bool:
    return bool(triggered_failure_flags(result))


def suggested_owner(result: Dict[str, Any], source: str) -> str:
    failure = str(result.get("failure_category") or "").lower()
    category = str(result.get("category") or "").lower()
    flags = set(triggered_failure_flags(result))

    if "metadata_complete=false" in flags:
        return "metadata_contract"
    if "source_filter_failed=true" in flags or "inferred_boundary_break=true" in flags:
        return "metadata_contract"
    if "path_correct=false" in flags or "path routing" in failure:
        return "retrieval_logic"
    if failure in {"wrong ranking", "retrieval miss", "wrong relation"}:
        return "retrieval_logic"
    if failure in {"wrong quantity", "source leakage"} and source in {"wikidata", "nasa"}:
        return "fixture_data"
    if "negative" in category or "source_isolation" in category:
        return "gold_set"
    if "top_k_expectation_met=false" in flags:
        return "retrieval_logic"
    return "unknown"


def extract_failures(report_name: str, source: str, report: Dict[str, Any]) -> List[Dict[str, Any]]:
    failures = []
    for result in report.get("results", []):
        if not isinstance(result, dict) or not is_failure_result(result):
            continue
        failures.append(
            {
                "report_name": report_name,
                "source": source,
                "id": result.get("id"),
                "query": result.get("query"),
                "category": result.get("category"),
                "query_kind": result.get("query_kind"),
                "expected_path": result.get("expected_path"),
                "actual_path": result.get("actual_path"),
                "expected_result": result.get("expected_result"),
                "returned_result": result.get("returned_result"),
                "failure_category": result.get("failure_category") or ", ".join(triggered_failure_flags(result)),
                "failure_flags": triggered_failure_flags(result),
                "source_metadata": source_metadata_from_result(result),
                "suggested_owner": suggested_owner(result, source),
            }
        )
    return failures


def load_reports(report_specs: Iterable[Dict[str, str]] = REPORT_SPECS) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    reports = []
    missing = []
    for spec in report_specs:
        path = spec["path"]
        if not os.path.exists(path):
            missing.append({"report_name": spec["report_name"], "source": spec["source"], "path": path})
            continue
        reports.append({**spec, "payload": load_json(path)})
    return reports, missing


def build_triage_payload(reports: List[Dict[str, Any]], missing_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    failures: List[Dict[str, Any]] = []
    report_summaries = []
    for report in reports:
        payload = report["payload"]
        summary = dict(payload.get("summary") or {})
        gates = dict(payload.get("gates") or {})
        report_summaries.append(
            {
                "report_name": report["report_name"],
                "source": report["source"],
                "path": os.path.relpath(report["path"], ROOT),
                "exact_accuracy": summary.get("exact_accuracy"),
                "source_filter_failure_count": summary.get("source_filter_failure_count"),
                "metadata_contract_break_count": summary.get("metadata_contract_break_count"),
                "inferred_boundary_break_count": summary.get("inferred_boundary_break_count"),
                "gates_passed": gates.get("passed"),
            }
        )
        if gates.get("passed") is False:
            failures.extend(extract_failures(report["report_name"], report["source"], payload))

    return {
        "status": "failures_found" if failures else "no_failures",
        "failure_count": len(failures),
        "reports": report_summaries,
        "missing_reports": missing_reports,
        "failures": failures,
    }


def markdown_table(rows: List[List[str]], headers: List[str]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        escaped = [str(cell).replace("\n", " ").replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


def render_triage_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Retrieval Failure Triage",
        "",
        "Generated from the latest single-source and source-expansion JSON reports.",
        "",
    ]
    if payload["missing_reports"]:
        lines.extend(["## Missing Reports", ""])
        for item in payload["missing_reports"]:
            lines.append(f"- `{item['report_name']}` ({item['source']}): `{item['path']}`")
        lines.append("")

    if not payload["failures"]:
        lines.extend(["## Result", "", "no failures", ""])
        return "\n".join(lines)

    lines.extend([f"## Summary", "", f"- failure_count: {payload['failure_count']}", ""])
    rows = []
    for item in payload["failures"]:
        rows.append(
            [
                item.get("report_name", ""),
                item.get("source", ""),
                item.get("id", ""),
                item.get("category", ""),
                item.get("query_kind", ""),
                item.get("failure_category", ""),
                item.get("suggested_owner", ""),
                compact(item.get("query")),
                compact(item.get("expected_result")),
                compact(item.get("returned_result")),
            ]
        )
    lines.extend(
        [
            markdown_table(
                rows,
                [
                    "report",
                    "source",
                    "id",
                    "category",
                    "kind",
                    "failure",
                    "owner",
                    "query",
                    "expected",
                    "returned",
                ],
            ),
            "",
        ]
    )
    return "\n".join(lines)


def backlog_priority(item: Dict[str, Any]) -> str:
    source = item.get("source")
    flags = set(item.get("failure_flags") or [])
    failure = str(item.get("failure_category") or "").lower()
    if source == "zh_wikipedia":
        return "P0"
    if flags.intersection({"metadata_complete=false", "source_filter_failed=true", "inferred_boundary_break=true", "path_correct=false"}):
        return "P1"
    if "path routing" in failure:
        return "P1"
    if source == "wikidata":
        return "P2"
    if source == "nasa":
        return "P3"
    return "P1"


def suspected_cause(item: Dict[str, Any]) -> str:
    owner = item.get("suggested_owner")
    failure = item.get("failure_category") or "unknown"
    if owner == "metadata_contract":
        return "Metadata/source boundary contract was not preserved for this returned record."
    if owner == "fixture_data":
        return "Shadow fixture or materialized sample data likely lacks the expected fact or empty expectation."
    if owner == "retrieval_logic":
        return f"Retrieval ranking/path logic selected a non-gold top result ({failure})."
    if owner == "gold_set":
        return "Gold expectation may be too strict or inconsistent with the current shadow fixture."
    return f"Needs triage; observed failure category is {failure}."


def proposed_fix(item: Dict[str, Any]) -> str:
    owner = item.get("suggested_owner")
    source = item.get("source")
    if owner == "metadata_contract":
        return "Normalize fallback/graph/chroma metadata and add a focused regression assertion."
    if owner == "fixture_data":
        return f"Audit `{source}` fixture triples/narratives and align the gold query expectation with auditable data."
    if owner == "retrieval_logic":
        return "Tune local retrieval scoring or graph/fallback selection for this query without changing gate thresholds."
    if owner == "gold_set":
        return "Review the query's expected empty/result contract and update only if the fixture proves the current gold is wrong."
    return "Inspect result trace and assign to gold_set, fixture_data, retrieval_logic, or metadata_contract."


def likely_files(item: Dict[str, Any]) -> List[str]:
    source = item.get("source")
    owner = item.get("suggested_owner")
    files = []
    if source == "zh_wikipedia":
        files.extend(["evaluation/single_source_retrieval_queries.json", "src/agent/llm_agent.py"])
    elif source in {"wikidata", "nasa"}:
        files.extend(
            [
                f"evaluation/source_expansion/{source}/{source}_queries.json",
                f"data/triples/{source}",
                "src/agent/llm_agent.py",
            ]
        )
    if owner == "metadata_contract":
        files.extend(["src/vector_store/chroma_store.py", "src/knowledge_graph/neo4j_loader.py"])
    if owner == "retrieval_logic":
        files.extend(["src/nlp/query_analyzer.py", "src/nlp/ontology.py"])
    return sorted(dict.fromkeys(files))


def render_backlog_markdown(payload: Dict[str, Any]) -> str:
    groups = {
        "P0": ("P0: single-source zh_wikipedia regression", []),
        "P1": ("P1: metadata/source_filter/path routing break", []),
        "P2": ("P2: Wikidata fixture/gold/retrieval failures", []),
        "P3": ("P3: NASA fixture/gold/retrieval failures", []),
    }
    for item in payload["failures"]:
        groups[backlog_priority(item)][1].append(item)

    lines = [
        "# Retrieval Repair Backlog",
        "",
        "Generated from `evaluation/eval_failure_triage.json`.",
        "",
        "Do not raise gate thresholds to hide these failures. Do not enable multi-source fusion as a repair shortcut.",
        "",
    ]
    if not payload["failures"]:
        lines.extend(["No failure backlog items. Current triage status: no failures.", ""])
        return "\n".join(lines)

    for _, (title, items) in groups.items():
        lines.extend([f"## {title}", ""])
        if not items:
            lines.extend(["No items.", ""])
            continue
        for item in items:
            lines.extend(
                [
                    f"### {item.get('id')}",
                    "",
                    f"- query id: `{item.get('id')}`",
                    f"- query: {item.get('query')}",
                    f"- expected vs actual: `{compact(item.get('expected_result'))}` vs `{compact(item.get('returned_result'))}`",
                    f"- suspected cause: {suspected_cause(item)}",
                    f"- proposed fix: {proposed_fix(item)}",
                    f"- files likely involved: {', '.join(f'`{path}`' for path in likely_files(item))}",
                    "",
                ]
            )
    return "\n".join(lines)


def main() -> int:
    configure_stdout()
    reports, missing_reports = load_reports()
    payload = build_triage_payload(reports, missing_reports)
    dump_json(TRIAGE_JSON, payload)
    write_text(TRIAGE_MD, render_triage_markdown(payload))
    write_text(BACKLOG_MD, render_backlog_markdown(payload))
    print(json.dumps({"triage_json": TRIAGE_JSON, "triage_md": TRIAGE_MD, "backlog_md": BACKLOG_MD, "failure_count": payload["failure_count"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

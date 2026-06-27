import json
import os
import re
import sys
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from src.agent.llm_agent import LLMAgent


DISABLED_SHADOW_SOURCES = ("wikidata", "nasa", "esa")
DEFAULT_QUERIES = (
    ("structured", "火卫一绕谁公转"),
    ("narrative", "火星大气成分"),
)
DEFAULT_REPORT = os.path.join(ROOT, "evaluation", "default_source_smoke_report.json")
SETTINGS_PATH = os.path.join(ROOT, "settings.json")


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def dump_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def normalize_source_value(record: Dict[str, Any]) -> str:
    return str(record.get("source_name") or record.get("source") or "").strip()


def flatten_records(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get("final_result"), list):
            return [item for item in value["final_result"] if isinstance(item, dict)]
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def result_has_disabled_source(records: Iterable[Dict[str, Any]]) -> bool:
    disabled = set(DISABLED_SHADOW_SOURCES)
    for record in records:
        if normalize_source_value(record) in disabled:
            return True
    return False


def assert_source_registry_boundary() -> List[Dict[str, Any]]:
    checks = [
        {
            "name": "active_source_is_zh_wikipedia",
            "passed": ACTIVE_SOURCE == "zh_wikipedia",
            "expected": "zh_wikipedia",
            "actual": ACTIVE_SOURCE,
        }
    ]
    for source in DISABLED_SHADOW_SOURCES:
        checks.append(
            {
                "name": f"{source}_registry_disabled",
                "passed": SOURCE_REGISTRY.get(source) == "disabled",
                "expected": "disabled",
                "actual": SOURCE_REGISTRY.get(source),
            }
        )
    return checks


def load_settings_text(settings_path: str = SETTINGS_PATH) -> str:
    if not os.path.exists(settings_path):
        return ""
    with open(settings_path, "r", encoding="utf-8") as handle:
        return handle.read()


def check_settings_key_hygiene(settings_path: str = SETTINGS_PATH) -> Dict[str, Any]:
    text = load_settings_text(settings_path)
    real_matches = re.findall(r"sk-[A-Za-z0-9_\-]{8,}", text)
    return {
        "name": "settings_has_no_real_sk_api_key",
        "passed": not real_matches,
        "expected": "no literal sk-* API key; ${TOLOLO_REMOTE_API_KEY} is allowed",
        "actual": "clean" if not real_matches else f"{len(real_matches)} literal key-like value(s)",
    }


def run_query(agent: Any, query_kind: str, query: str, source_filter: Optional[List[str]] = None) -> Dict[str, Any]:
    if query_kind == "structured":
        trace = agent.search_neo4j_trace(query, limit=5, source_filter=source_filter)
        records = flatten_records(trace)
        return {
            "query_kind": query_kind,
            "query": query,
            "source_filter": source_filter,
            "actual_path": trace.get("final_source") if isinstance(trace, dict) else None,
            "records": records,
        }
    records = flatten_records(agent.search_chroma(query, top_k=5, source_filter=source_filter))
    return {
        "query_kind": query_kind,
        "query": query,
        "source_filter": source_filter,
        "actual_path": "chroma_or_fallback",
        "records": records,
    }


def default_query_checks(agent: Any) -> List[Dict[str, Any]]:
    checks = []
    for query_kind, query in DEFAULT_QUERIES:
        result = run_query(agent, query_kind, query)
        leaked = result_has_disabled_source(result["records"])
        checks.append(
            {
                "name": f"default_{query_kind}_does_not_return_shadow_source",
                "passed": not leaked,
                "query": query,
                "source_filter": None,
                "actual_path": result["actual_path"],
                "returned_sources": sorted({normalize_source_value(record) for record in result["records"] if normalize_source_value(record)}),
                "record_count": len(result["records"]),
            }
        )
    return checks


def explicit_filter_isolation_checks(agent: Any) -> List[Dict[str, Any]]:
    checks = []
    for source in DISABLED_SHADOW_SOURCES:
        for query_kind, query in DEFAULT_QUERIES:
            explicit = run_query(agent, query_kind, query, source_filter=[source])
            after_default = run_query(agent, query_kind, query)
            leaked = result_has_disabled_source(after_default["records"])
            checks.append(
                {
                    "name": f"explicit_{source}_{query_kind}_does_not_pollute_default",
                    "passed": not leaked,
                    "query": query,
                    "explicit_source_filter": [source],
                    "explicit_record_count": len(explicit["records"]),
                    "default_sources_after_explicit": sorted(
                        {normalize_source_value(record) for record in after_default["records"] if normalize_source_value(record)}
                    ),
                    "default_record_count_after_explicit": len(after_default["records"]),
                }
            )
    return checks


def build_report(
    registry_checks: List[Dict[str, Any]],
    default_checks: List[Dict[str, Any]],
    explicit_checks: List[Dict[str, Any]],
    settings_check: Dict[str, Any],
    errors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    all_checks = registry_checks + default_checks + explicit_checks + [settings_check]
    errors = errors or []
    return {
        "active_source": ACTIVE_SOURCE,
        "disabled_shadow_sources": list(DISABLED_SHADOW_SOURCES),
        "passed": all(item.get("passed") for item in all_checks) and not errors,
        "errors": errors,
        "checks": {
            "source_registry": registry_checks,
            "default_queries": default_checks,
            "explicit_filter_isolation": explicit_checks,
            "settings_key_hygiene": settings_check,
        },
    }


def run_smoke(
    agent_factory: Callable[[], Any] = LLMAgent,
    settings_path: str = SETTINGS_PATH,
    output_path: str = DEFAULT_REPORT,
    write_report: bool = True,
) -> Tuple[Dict[str, Any], int]:
    errors: List[str] = []
    registry_checks = assert_source_registry_boundary()
    default_checks: List[Dict[str, Any]] = []
    explicit_checks: List[Dict[str, Any]] = []
    settings_check = check_settings_key_hygiene(settings_path)

    try:
        agent = agent_factory()
        default_checks = default_query_checks(agent)
        explicit_checks = explicit_filter_isolation_checks(agent)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    report = build_report(registry_checks, default_checks, explicit_checks, settings_check, errors=errors)
    if write_report:
        dump_json(output_path, report)
    return report, 0 if report["passed"] else 1


def main() -> int:
    configure_stdout()
    report, exit_code = run_smoke()
    print(json.dumps({"report": DEFAULT_REPORT, "passed": report["passed"], "errors": report["errors"]}, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

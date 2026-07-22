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
from scripts.evaluate_nasa_shadow_json_retrieval import matches_oracle, retrieve


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


def shadow_paths(shadow_dir: Path) -> Dict[str, Path]:
    return {
        "triples": shadow_dir / "triples_preview.json",
        "narratives": shadow_dir / "narratives_preview.json",
        "manifest": shadow_dir / "package_manifest.json",
    }


def blocked_report(reason: str, shadow_dir: Path, eval_report_path: Path) -> Dict[str, Any]:
    return {
        "phase": "Phase 49",
        "mode": "nasa_shadow_query_chain_adapter_dry_run",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "ready": False,
        "blocked_reason": reason,
        "shadow_dir": str(shadow_dir),
        "eval_report_path": str(eval_report_path),
        "adapter_mappings": [],
        "mapping_count": 0,
        "active_source": ACTIVE_SOURCE,
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "data_write": False,
    }


def top_result_for_case(results: Sequence[Dict[str, Any]], oracle: Dict[str, Any]) -> Dict[str, Any]:
    for result in results:
        if matches_oracle(result, oracle):
            return result
    return dict(results[0]) if results else {}


def payload_for_result(query: str, result: Dict[str, Any], result_count: int) -> Dict[str, Any]:
    return {
        "query": query,
        "source_id": SOURCE_ID,
        "result_count": result_count,
        "top_result": {
            "kind": result.get("kind", ""),
            "subject": result.get("subject") or result.get("page_title", ""),
            "relation": result.get("predicate", ""),
            "object": result.get("object", ""),
            "evidence": result.get("evidence") or result.get("snippet", ""),
            "source_url": result.get("source_url", ""),
        },
    }


def build_mapping(case: Dict[str, Any], triples: Sequence[Dict[str, Any]], narratives: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    query = str(case.get("query", ""))
    oracle = case.get("oracle", {}) if isinstance(case.get("oracle"), dict) else {}
    results = retrieve(query, triples, narratives)
    top_result = top_result_for_case(results, oracle)
    payload = payload_for_result(query, top_result, len(results))
    return {
        "case_id": case.get("case_id", ""),
        "user_query": query,
        "proposed_adapter_function": "nasa_shadow_json_retrieve",
        "proposed_adapter_input": {
            "query": query,
            "source_id": SOURCE_ID,
            "mode": "dry_run_json_only",
            "shadow_dir": "data/triples_shadow/nasa",
        },
        "json_shadow_result_count": len(results),
        "expected_retrieval_payload": payload,
        "oracle": oracle,
        "oracle_satisfied": bool(top_result) and matches_oracle(top_result, oracle),
    }


def query_chain_notes() -> Dict[str, Any]:
    return {
        "observed_entrypoints": [
            "src.gui.main_window: source selection forwards source_name toward the agent tab workflow",
            "src.agent.llm_agent: LLMAgent(source_name=...) owns single-source retrieval",
            "src.agent.llm_agent: _search_single_source_bundle(source_name, query) calls graph and narrative retrieval",
            "src.agent.llm_agent: local JSON fallback already exists for formal data/triples namespaces",
        ],
        "minimal_future_adapter_point": "Add an explicit NASA shadow dry-run branch near LLMAgent._search_single_source_bundle or behind a separate review-only command path.",
        "forbidden_in_phase49": [
            "do not enable nasa in SOURCE_REGISTRY",
            "do not change ACTIVE_SOURCE",
            "do not query vector or graph databases",
            "do not write data/triples or data/triples_shadow",
        ],
    }


def build_adapter_preview(*, shadow_dir: Path, eval_report_path: Path) -> Dict[str, Any]:
    paths = shadow_paths(shadow_dir)
    missing_shadow = [name for name, path in paths.items() if not path.exists()]
    if missing_shadow or not eval_report_path.exists():
        report = blocked_report("missing_shadow_or_eval_report", shadow_dir, eval_report_path)
        report["missing_shadow_files"] = missing_shadow
        report["eval_report_exists"] = eval_report_path.exists()
        return report

    triples = read_json(paths["triples"])
    narratives = read_json(paths["narratives"])
    manifest = read_json(paths["manifest"])
    eval_report = read_json(eval_report_path)
    if not isinstance(triples, list) or not isinstance(narratives, list) or not isinstance(manifest, dict) or not isinstance(eval_report, dict):
        return blocked_report("invalid_shadow_or_eval_json", shadow_dir, eval_report_path)

    cases = eval_report.get("eval_cases", [])
    if not isinstance(cases, list) or not cases:
        return blocked_report("missing_eval_cases", shadow_dir, eval_report_path)

    mappings = [build_mapping(case, triples, narratives) for case in cases[:12]]
    ready = bool(mappings) and all(item.get("oracle_satisfied") for item in mappings)
    return {
        "phase": "Phase 49",
        "mode": "nasa_shadow_query_chain_adapter_dry_run",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "ready": ready,
        "blocked_reason": "" if ready else "adapter_mapping_oracle_failure",
        "shadow_dir": str(shadow_dir),
        "eval_report_path": str(eval_report_path),
        "local_artifact": True,
        "counts": {
            "items": int(manifest.get("items", 0) or 0),
            "triples": len(triples),
            "narratives": len(narratives),
        },
        "query_chain_notes": query_chain_notes(),
        "adapter_mappings": mappings,
        "mapping_count": len(mappings),
        "active_source": ACTIVE_SOURCE,
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "data_write": False,
        "recommended_next_action": "review_dry_run_adapter_before_any_gui_or_database_integration" if ready else "review_failed_adapter_mappings",
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# NASA shadow query-chain adapter dry-run",
        "",
        "Phase 49 maps NASA shadow JSON eval cases into the payload shape a future retrieval or GUI path could consume.",
        "This is a dry-run report only: no source switch, no database calls, and no data writes.",
        "",
        f"- ready: `{report.get('ready')}`",
        f"- blocked_reason: `{report.get('blocked_reason', '')}`",
        f"- mapping_count: `{report.get('mapping_count', 0)}`",
        f"- active_source: `{report.get('active_source')}`",
        f"- formal_default_triples_write: `{report.get('formal_default_triples_write')}`",
        f"- chroma_write: `{report.get('chroma_write')}`",
        f"- neo4j_write: `{report.get('neo4j_write')}`",
        f"- data_write: `{report.get('data_write')}`",
        "",
        "## Minimal Future Adapter Point",
        "",
        f"- {report.get('query_chain_notes', {}).get('minimal_future_adapter_point', '')}",
        "",
        "## Mapping Preview",
        "",
        "| case | query | results | source_url |",
        "| --- | --- | ---: | --- |",
    ]
    for item in report.get("adapter_mappings", []):
        payload = item.get("expected_retrieval_payload", {})
        top = payload.get("top_result", {})
        lines.append(
            f"| `{item.get('case_id')}` | `{item.get('user_query')}` | "
            f"{payload.get('result_count', 0)} | `{top.get('source_url', '')}` |"
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Preview NASA shadow JSON-only adapter payloads for the real query chain.")
    parser.add_argument("--shadow-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument("--eval-report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_json_retrieval_eval_phase48.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_query_chain_adapter_phase49.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_shadow_query_chain_adapter_phase49.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json):
        print("out-json must stay under evaluation/four_source_expansion/", file=sys.stderr)
        return 2
    if not output_allowed(out_md, allow_docs=True):
        print("out-md must stay under docs/ or evaluation/four_source_expansion/", file=sys.stderr)
        return 2

    report = build_adapter_preview(shadow_dir=Path(args.shadow_dir), eval_report_path=Path(args.eval_report_json))
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    print(
        f"ready={report['ready']} mappings={report['mapping_count']} blocked={report['blocked_reason']} "
        f"active_source={ACTIVE_SOURCE}"
    )
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

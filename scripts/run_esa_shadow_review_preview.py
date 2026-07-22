from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


SOURCE_ID = "esa"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return relative.parts[:2] == ("evaluation", "four_source_expansion") or (allow_docs and relative.parts[:1] == ("docs",))


def blocked(reason: str, eval_report_path: Path, shadow_dir: Path) -> Dict[str, Any]:
    return {
        "phase": "Phase 73",
        "mode": "esa_shadow_review_only_cli",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "ready": False,
        "blocked_reason": reason,
        "eval_report_path": str(eval_report_path),
        "shadow_dir": str(shadow_dir),
        "adapter_mappings": [],
        "mapping_count": 0,
        "review_only_required": True,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def top_result(case_result: Dict[str, Any]) -> Dict[str, Any]:
    rows = case_result.get("top_results", []) if isinstance(case_result.get("top_results"), list) else []
    return rows[0] if rows else {}


def build_review_report(*, eval_report_path: Path, shadow_dir: Path, review_only: bool) -> Dict[str, Any]:
    if review_only is not True:
        return blocked("review_only_flag_required", eval_report_path, shadow_dir)
    eval_report = read_json(eval_report_path)
    if not isinstance(eval_report, dict) or eval_report.get("ready") is not True:
        return blocked("phase72_eval_not_ready", eval_report_path, shadow_dir)
    mappings = []
    for result in eval_report.get("eval", {}).get("case_results", []):
        top = top_result(result)
        mappings.append(
            {
                "query": result.get("query", ""),
                "source_id": SOURCE_ID,
                "result_count": result.get("hit_count", 0),
                "oracle_satisfied": bool(result.get("passed")),
                "top_result": top,
                "evidence": top.get("evidence") or top.get("snippet", ""),
                "source_url": top.get("source_url", ""),
            }
        )
    return {
        "phase": "Phase 73",
        "mode": "esa_shadow_review_only_cli",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "ready": bool(mappings) and all(row["oracle_satisfied"] for row in mappings),
        "blocked_reason": "" if mappings else "no_mappings",
        "eval_report_path": str(eval_report_path),
        "shadow_dir": str(shadow_dir),
        "adapter_mappings": mappings,
        "mapping_count": len(mappings),
        "review_only_required": True,
        "review_only": True,
        "default_query_path_changed": False,
        "gui_default_behavior_changed": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def render_md(report: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# ESA shadow review-only query preview CLI",
            "",
            f"- ready: `{report.get('ready')}`",
            f"- blocked_reason: `{report.get('blocked_reason', '')}`",
            f"- mapping_count: `{report.get('mapping_count', 0)}`",
            f"- review_only_required: `{report.get('review_only_required')}`",
            f"- active_source: `{report.get('active_source')}`",
            f"- esa_registry: `{report.get('registry', {}).get('esa')}`",
            f"- chroma_write: `{report.get('chroma_write')}`",
            f"- neo4j_write: `{report.get('neo4j_write')}`",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit review-only ESA shadow query preview.")
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument("--shadow-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument("--eval-report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_shadow_readiness_eval_phase72.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_shadow_review_preview_cli_phase73.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "esa_shadow_review_preview_cli_phase73.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = build_review_report(eval_report_path=Path(args.eval_report_json), shadow_dir=Path(args.shadow_dir), review_only=bool(args.review_only))
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"ready={report.get('ready')} mappings={report.get('mapping_count', 0)} blocked={report.get('blocked_reason', '')}")
    return 0 if report.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())

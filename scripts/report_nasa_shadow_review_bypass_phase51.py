from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.nasa_shadow_review import SOURCE_ID, run_nasa_shadow_review_preview


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    parts = list(path.resolve().parts)
    if allow_docs and "docs" in parts:
        return True
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# NASA shadow review-only query bypass",
        "",
        "Phase 51 adds an explicit review-only code entry point near the query layer. It is not wired into the default GUI, LLMAgent, Chroma, or Neo4j path.",
        "",
        f"- ready: `{report.get('ready')}`",
        f"- blocked_reason: `{report.get('blocked_reason', '')}`",
        f"- mapping_count: `{report.get('mapping_count', 0)}`",
        f"- review_only_required: `{report.get('review_only_required')}`",
        f"- review_only: `{report.get('review_only')}`",
        f"- active_source: `{report.get('active_source')}`",
        f"- default_query_path_changed: `{report.get('default_query_path_changed')}`",
        f"- gui_default_behavior_changed: `{report.get('gui_default_behavior_changed')}`",
        f"- formal_default_triples_write: `{report.get('formal_default_triples_write')}`",
        f"- chroma_write: `{report.get('chroma_write')}`",
        f"- neo4j_write: `{report.get('neo4j_write')}`",
        f"- data_write: `{report.get('data_write')}`",
        "",
        "## Review Payload Preview",
        "",
        "| case | query | results | top source URL |",
        "| --- | --- | ---: | --- |",
    ]
    for item in report.get("adapter_mappings", []):
        payload = item.get("expected_retrieval_payload", {})
        top = payload.get("top_result", {})
        lines.append(
            f"| `{item.get('case_id', '')}` | `{item.get('user_query', '')}` | "
            f"{payload.get('result_count', 0)} | `{top.get('source_url', '')}` |"
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Render NASA shadow review-only query bypass report.")
    parser.add_argument("--shadow-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument(
        "--eval-report-json",
        default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_json_retrieval_eval_phase48.json"),
    )
    parser.add_argument(
        "--out-json",
        default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_review_bypass_phase51.json"),
    )
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_shadow_review_bypass_phase51.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json):
        print("out-json must stay under evaluation/four_source_expansion/", file=sys.stderr)
        return 2
    if not output_allowed(out_md, allow_docs=True):
        print("out-md must stay under docs/ or evaluation/four_source_expansion/", file=sys.stderr)
        return 2

    report = run_nasa_shadow_review_preview(
        shadow_dir=Path(args.shadow_dir),
        eval_report_path=Path(args.eval_report_json),
        review_only=True,
    )
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    print(
        f"ready={report.get('ready')} mappings={report.get('mapping_count', 0)} "
        f"blocked={report.get('blocked_reason', '')}"
    )
    return 0 if report.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.report_nasa_shadow_review_bypass_phase51 import render_markdown
from src.agent.nasa_shadow_review import SOURCE_ID, run_nasa_shadow_review_preview


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    parts = list(path.resolve().parts)
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1)) or (
        allow_docs and "docs" in parts
    )


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit review-only NASA shadow query preview.")
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument("--shadow-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument("--eval-report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_json_retrieval_eval_phase63.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_review_preview_cli_phase66.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_shadow_review_preview_cli_phase66.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    if not args.review_only:
        report = run_nasa_shadow_review_preview(shadow_dir=args.shadow_dir, eval_report_path=args.eval_report_json, review_only=False)
        report["blocked_reason"] = "review_only_flag_required"
        write_json(out_json, report)
        write_text(out_md, render_markdown(report))
        print("ready=False mappings=0 blocked=review_only_flag_required")
        return 2

    report = run_nasa_shadow_review_preview(shadow_dir=args.shadow_dir, eval_report_path=args.eval_report_json, review_only=True)
    report["phase"] = "Phase 66"
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    print(f"ready={report.get('ready')} mappings={report.get('mapping_count', 0)} blocked={report.get('blocked_reason', '')}")
    return 0 if report.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())

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
from scripts.materialize_manifest_raw_records import convert_raw_payload, safe_name


SOURCE_ID = "nasa"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def under_four_source_expansion(path: Path) -> bool:
    parts = list(path.resolve().parts)
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1))


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    parts = list(path.resolve().parts)
    if allow_docs and "docs" in parts:
        return True
    return under_four_source_expansion(path)


def selected_preview_items(preview: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        item
        for item in preview.get("items", []) if isinstance(preview.get("items"), list)
        if item.get("source_id") == SOURCE_ID and item.get("quality_triage") == "accepted"
    ]


def trial_payload(raw_path: Path, preview_item: Dict[str, Any]) -> Dict[str, Any]:
    raw = read_json(raw_path)
    if not isinstance(raw, dict):
        raise ValueError("raw_json_not_object")
    converted = convert_raw_payload(SOURCE_ID, raw)
    title = str(converted.get("title") or raw.get("title") or raw_path.stem)
    return {
        "trial": True,
        "phase": "Phase 43",
        "source_id": SOURCE_ID,
        "raw_path": str(raw_path),
        "source_url": converted.get("source_url") or raw.get("source_url") or raw.get("url") or preview_item.get("url", ""),
        "title": title,
        "quality_triage": preview_item.get("quality_triage"),
        "quality_score": preview_item.get("quality_score"),
        "triples": converted.get("triples", []),
        "narratives": converted.get("narratives", []),
        "formal_write": False,
    }


def build_report(
    *,
    preview_json: Path,
    out_dir: Path,
    limit: int,
    root: Path = ROOT,
) -> Dict[str, Any]:
    preview = read_json(preview_json)
    selected = selected_preview_items(preview if isinstance(preview, dict) else {})
    out_dir.mkdir(parents=True, exist_ok=True)
    processed = failed = triples = narratives = 0
    outputs: List[str] = []
    errors: List[Dict[str, Any]] = []

    for index, item in enumerate(selected[: max(0, limit)], start=1):
        raw_path = Path(str(item.get("raw_path") or ""))
        if not raw_path.exists():
            failed += 1
            errors.append({"raw_path": str(raw_path), "error": "missing_raw", "source_id": SOURCE_ID})
            continue
        try:
            payload = trial_payload(raw_path, item)
            title = str(payload.get("title") or raw_path.stem)
            output = out_dir / f"{index:02d}_{safe_name(title)}.json"
            write_json(output, payload)
            processed += 1
            triples += len(payload.get("triples", []))
            narratives += len(payload.get("narratives", []))
            outputs.append(str(output))
        except Exception as exc:
            failed += 1
            errors.append({"raw_path": str(raw_path), "error": str(exc), "type": type(exc).__name__, "source_id": SOURCE_ID})

    action = (
        "review_shadow_trial_outputs_before_formal_materialization"
        if processed > 0 and failed <= max(1, processed // 10)
        else "manual_review_before_shadow_trial"
    )
    return {
        "phase": "Phase 43",
        "mode": "nasa_limited_shadow_triples_trial",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "preview_json": str(preview_json),
        "input_raw_count": len(selected),
        "processed_count": processed,
        "limit": limit,
        "triples_generated": triples,
        "narratives_generated": narratives,
        "failed": failed,
        "errors": errors,
        "out_dir": str(out_dir),
        "outputs": outputs,
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "formal_triples_write": False,
        "formal_narratives_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "network": False,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "recommended_next_action": action,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# NASA shadow triples trial",
        "",
        "本报告只处理 Phase 42 中 NASA accepted 的新增 raw，产物写在 evaluation 隔离目录，不写正式 data/triples。",
        "",
        f"- source: `{report['source_id']}`",
        f"- input raw: `{report['input_raw_count']}`",
        f"- processed: `{report['processed_count']}`",
        f"- triples generated: `{report['triples_generated']}`",
        f"- narratives generated: `{report['narratives_generated']}`",
        f"- failed: `{report['failed']}`",
        f"- out_dir: `{report['out_dir']}`",
        f"- recommended next action: `{report['recommended_next_action']}`",
        "",
        "## Outputs",
        "",
    ]
    for output in report["outputs"][:25]:
        lines.append(f"- `{output}`")
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for error in report["errors"]:
            lines.append(f"- `{error.get('raw_path')}`: {error.get('error')}")
    lines.extend(["", "## Safety", ""])
    for key in ("formal_triples_write", "formal_narratives_write", "chroma_write", "neo4j_write", "network", "active_source_unchanged"):
        lines.append(f"- {key}: `{report[key]}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Create isolated NASA shadow triples/narratives trial outputs from Phase 42 accepted raw.")
    parser.add_argument("--preview-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "new_raw_materialization_preview_phase42.json"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_triples_trial_phase43"))
    parser.add_argument("--report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_triples_trial_phase43.json"))
    parser.add_argument("--report-md", default=str(ROOT / "docs" / "nasa_shadow_triples_trial_phase43.md"))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    report_json = Path(args.report_json)
    report_md = Path(args.report_md)
    if not output_allowed(out_dir) or not output_allowed(report_json) or not output_allowed(report_md, allow_docs=True):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    if args.limit <= 0:
        print("limit must be positive", file=sys.stderr)
        return 2

    report = build_report(preview_json=Path(args.preview_json), out_dir=out_dir, limit=args.limit)
    write_json(report_json, report)
    write_text(report_md, render_markdown(report))
    print(
        f"source={report['source_id']} input={report['input_raw_count']} processed={report['processed_count']} "
        f"triples={report['triples_generated']} narratives={report['narratives_generated']} "
        f"failed={report['failed']} active_source={ACTIVE_SOURCE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

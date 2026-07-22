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


DEFAULT_TARGETS = ("zh_wikipedia", "nasa", "esa", "wikidata")
STATUS_REPORT = "evaluation/source_expansion/source_expansion_status_report.json"


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


def output_allowed(path: Path) -> bool:
    parts = set(path.resolve().parts)
    return "evaluation" in parts or "docs" in parts


def count_files(path: Path, pattern: str = "*.json") -> int:
    return len(list(path.glob(pattern))) if path.exists() else 0


def source_counts(root: Path, source: str, status_report: Dict[str, Any]) -> tuple[int, int, int, List[str]]:
    warnings: List[str] = []
    status_item = status_report.get(source) if isinstance(status_report.get(source), dict) else {}
    if status_item:
        return (
            int(status_item.get("raw_count") or 0),
            int(status_item.get("triple_count") or 0),
            int(status_item.get("narrative_count") or 0),
            warnings,
        )

    raw_dir = root / "data" / "raw_json" / source
    triple_dir = root / "data" / "triples" / source
    if not raw_dir.exists():
        warnings.append(f"missing raw directory: {raw_dir.as_posix()}")
    if not triple_dir.exists():
        warnings.append(f"missing triples directory: {triple_dir.as_posix()}")
    raw_count = count_files(raw_dir)
    triple_count = count_files(triple_dir, "*_triples.json")
    narrative_count = count_files(triple_dir, "*_narratives.json")
    if source == "zh_wikipedia":
        warnings.append("zh_wikipedia counts are directory-based baseline estimates; no source expansion status item")
    return raw_count, triple_count, narrative_count, warnings


def recommended_action(source: str, mode: str, raw_count: int, warnings: List[str]) -> str:
    if any("missing" in warning for warning in warnings):
        return "needs_manifest_fix"
    if source == ACTIVE_SOURCE and mode == "active":
        return "keep_active_baseline"
    if raw_count > 0:
        return "ready_for_batch_preview"
    return "expand_shadow_preview"


def source_plan(root: Path, source: str, batch_size: int, status_report: Dict[str, Any]) -> Dict[str, Any]:
    raw_count, triple_count, narrative_count, warnings = source_counts(root, source, status_report)
    mode = SOURCE_REGISTRY.get(source, "unknown")
    shadow = source != ACTIVE_SOURCE
    materialization_scope = "shadow_only" if shadow else "formal_candidate"
    safeguards = [
        "dry_run_plan_only",
        "quality_gate_before_materialization",
        "no_default_source_cutover",
    ]
    if shadow:
        safeguards.append("shadow_namespace_only")
    else:
        safeguards.append("keep_active_baseline")
    return {
        "source_id": source,
        "current_raw_count": raw_count,
        "current_triple_count": triple_count,
        "current_narrative_count": narrative_count,
        "mode": mode,
        "proposed_batch_size": batch_size,
        "proposed_next_target_count": raw_count + batch_size,
        "quality_gate_required": True,
        "materialization_scope": materialization_scope,
        "recommended_action": recommended_action(source, str(mode), raw_count, warnings),
        "risks": [
            "quality drift if batch is accepted without review",
            "default answer pollution if disabled sources are promoted too early",
        ],
        "safeguards": safeguards,
        "warnings": warnings,
    }


def build_plan(
    *,
    root: Path = ROOT,
    targets: Sequence[str] = DEFAULT_TARGETS,
    batch_size: int = 50,
) -> Dict[str, Any]:
    status_path = Path(root) / STATUS_REPORT
    status_report = read_json(status_path)
    sources = [source_plan(Path(root), source, batch_size, status_report) for source in targets]
    return {
        "phase": "Phase 37",
        "mode": "four_source_batch_expansion_dry_run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in DEFAULT_TARGETS},
        "status_report": {
            "path": STATUS_REPORT,
            "status": "present" if status_path.exists() else "missing",
        },
        "summary": {
            "targets": len(sources),
            "batch_size": batch_size,
            "formal_candidate_sources": [item["source_id"] for item in sources if item["materialization_scope"] == "formal_candidate"],
            "shadow_only_sources": [item["source_id"] for item in sources if item["materialization_scope"] == "shadow_only"],
        },
        "sources": sources,
        "safety_boundaries": [
            "This is a dry-run planning report only.",
            "No network probe, no preview run, no data pipeline write.",
            "nasa/esa/wikidata remain disabled and shadow-only.",
            "ACTIVE_SOURCE remains zh_wikipedia.",
            "Each proposed batch must pass quality review before any later materialization.",
        ],
        "next_steps": [
            "Run per-source frontier preview with explicit limits if a batch is approved.",
            "Review quality triage and rejected samples before any raw materialization.",
            "Keep nasa/esa/wikidata in shadow reports until cutover is separately approved.",
        ],
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# 四源扩批计划",
        "",
        "本报告只做 dry-run / preview 计划，不联网、不执行采集、不写正式数据管线。",
        "",
        f"- phase: `{report['phase']}`",
        f"- active_source: `{report['active_source']}`",
        f"- batch_size: `{report['summary']['batch_size']}`",
        f"- status_report: `{report['status_report']['path']}` ({report['status_report']['status']})",
        "",
        "## 当前规模与下一批计划",
        "",
        "| source | mode | raw | triples | narratives | next target | scope | action |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for item in report["sources"]:
        lines.append(
            f"| {item['source_id']} | `{item['mode']}` | {item['current_raw_count']} | "
            f"{item['current_triple_count']} | {item['current_narrative_count']} | "
            f"{item['proposed_next_target_count']} | `{item['materialization_scope']}` | "
            f"`{item['recommended_action']}` |"
        )
    lines.extend(["", "## 安全边界", ""])
    for boundary in report["safety_boundaries"]:
        lines.append(f"- {boundary}")
    lines.extend(["", "## 分源提示", ""])
    for item in report["sources"]:
        warnings = "; ".join(item["warnings"]) if item["warnings"] else "none"
        lines.append(f"- `{item['source_id']}`: safeguards={', '.join(item['safeguards'])}; warnings={warnings}")
    lines.extend(["", "## 下一步", ""])
    for step in report["next_steps"]:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Plan controlled four-source batch expansion.")
    parser.add_argument("--targets", nargs="*", default=list(DEFAULT_TARGETS))
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "four_source_batch_plan_phase37.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_batch_expansion_plan.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md):
        print("outputs must stay under evaluation/ or docs/", file=sys.stderr)
        return 2
    if args.batch_size <= 0:
        print("batch-size must be positive", file=sys.stderr)
        return 2

    report = build_plan(targets=args.targets, batch_size=args.batch_size)
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    print(
        f"sources={len(report['sources'])} batch_size={args.batch_size} "
        f"active_source={report['active_source']} shadow_only={len(report['summary']['shadow_only_sources'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

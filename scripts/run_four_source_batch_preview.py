from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


QUALITY_PREVIEW = "evaluation/source_quality/{source}_frontier_quality_preview.json"


def read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def output_allowed(path: Path) -> bool:
    resolved = path.resolve()
    parts = list(resolved.parts)
    if "docs" in parts:
        return True
    try:
        rel = resolved.relative_to(ROOT)
        return len(rel.parts) >= 2 and rel.parts[0] == "evaluation" and rel.parts[1] == "four_source_expansion"
    except ValueError:
        return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1))


def safety_flags() -> Dict[str, bool]:
    return {
        "formal_pipeline_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
    }


def source_from_plan(plan: Dict[str, Any], source_id: str) -> Dict[str, Any]:
    for item in plan.get("sources", []):
        if item.get("source_id") == source_id:
            return item if isinstance(item, dict) else {}
    return {}


def limited_triage_counts(records: Sequence[Dict[str, Any]], limit: int) -> Dict[str, int]:
    counter: Counter[str] = Counter()
    for record in list(records)[:limit]:
        counter[str(record.get("quality_triage") or "unknown")] += 1
    return dict(sorted(counter.items()))


def reused_quality_item(root: Path, source_id: str, plan_item: Dict[str, Any], batch_size: int) -> Dict[str, Any]:
    path = root / QUALITY_PREVIEW.format(source=source_id)
    payload = read_json(path)
    if not payload:
        return skipped_item(
            source_id,
            plan_item,
            reason=f"missing reusable quality preview: {QUALITY_PREVIEW.format(source=source_id)}",
        )

    accepted_records = payload.get("accepted", []) if isinstance(payload.get("accepted"), list) else []
    triage = limited_triage_counts(accepted_records, batch_size)
    candidate_count = min(int(payload.get("accepted_count") or len(accepted_records)), batch_size)
    skipped = int(payload.get("skipped_count") or 0)
    rejected = triage.get("rejected", 0)
    review_needed = triage.get("review_needed", 0)
    exploratory = triage.get("exploratory", 0)
    accepted = triage.get("accepted", 0)
    action = "needs_manual_review" if rejected or review_needed or exploratory else "raw_shadow_ingest_candidate"
    if source_id in {"nasa", "esa"} and rejected == 0:
        action = "raw_shadow_ingest_candidate"
    if source_id == "wikidata":
        action = "needs_manual_review"
    return {
        "source_id": source_id,
        "mode": SOURCE_REGISTRY.get(source_id, plan_item.get("mode", "unknown")),
        "preview_execution": "offline_reused",
        "candidate_count": candidate_count,
        "accepted": accepted,
        "review_needed": review_needed,
        "exploratory": exploratory,
        "rejected": rejected,
        "skipped": skipped,
        "quality_gate_summary": {
            "source_report": QUALITY_PREVIEW.format(source=source_id),
            "triage_counts": triage,
            "top_reasons": payload.get("quality_summary", {}).get("top_reasons", {})
            if isinstance(payload.get("quality_summary"), dict)
            else {},
        },
        "recommended_next_action": action,
        "safety_flags": safety_flags(),
    }


def skipped_item(source_id: str, plan_item: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "source_id": source_id,
        "mode": SOURCE_REGISTRY.get(source_id, plan_item.get("mode", "unknown")),
        "preview_execution": "skipped_with_reason",
        "candidate_count": 0,
        "accepted": 0,
        "review_needed": 0,
        "exploratory": 0,
        "rejected": 0,
        "skipped": 0,
        "quality_gate_summary": {"reason": reason, "triage_counts": {}},
        "recommended_next_action": "keep_baseline" if source_id == ACTIVE_SOURCE else "needs_manifest_fix",
        "safety_flags": safety_flags(),
    }


def build_preview(
    *,
    plan_path: Path,
    root: Path = ROOT,
    batch_size: int = 50,
    offline_only: bool = True,
) -> Dict[str, Any]:
    plan = read_json(plan_path)
    plan_sources = plan.get("sources", []) if isinstance(plan.get("sources"), list) else []
    source_ids = [str(item.get("source_id")) for item in plan_sources if item.get("source_id")]
    if not source_ids:
        source_ids = ["zh_wikipedia", "nasa", "esa", "wikidata"]

    sources: List[Dict[str, Any]] = []
    for source_id in source_ids:
        plan_item = source_from_plan(plan, source_id)
        if source_id == ACTIVE_SOURCE:
            sources.append(skipped_item(source_id, plan_item, "active baseline source; no batch preview without separate formal approval"))
            continue
        sources.append(reused_quality_item(root, source_id, plan_item, batch_size))

    action_counts = Counter(item["recommended_next_action"] for item in sources)
    return {
        "phase": "Phase 38",
        "mode": "four_source_batch_preview_offline_reuse",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_source": ACTIVE_SOURCE,
        "offline_only": bool(offline_only),
        "plan_json": str(plan_path),
        "batch_size": batch_size,
        "summary": {
            "sources": len(sources),
            "candidate_count": sum(int(item["candidate_count"]) for item in sources),
            "accepted": sum(int(item["accepted"]) for item in sources),
            "review_needed": sum(int(item["review_needed"]) for item in sources),
            "exploratory": sum(int(item["exploratory"]) for item in sources),
            "rejected": sum(int(item["rejected"]) for item in sources),
            "recommended_actions": dict(sorted(action_counts.items())),
        },
        "sources": sources,
        "safety_boundaries": [
            "offline-only report reuse; no network call",
            "no collection execution",
            "no formal raw/triples/vector/graph writes",
            "nasa/esa/wikidata remain disabled and shadow-only",
            "zh_wikipedia remains active baseline",
        ],
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# 四源 batch preview 质量报告",
        "",
        "本报告复用本地已有 frontier quality preview，不联网、不执行采集、不写正式数据管线。",
        "",
        f"- phase: `{report['phase']}`",
        f"- active_source: `{report['active_source']}`",
        f"- batch_size: `{report['batch_size']}`",
        f"- offline_only: `{report['offline_only']}`",
        "",
        "## Preview 摘要",
        "",
        "| source | mode | execution | candidates | accepted | review_needed | exploratory | rejected | action |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["sources"]:
        lines.append(
            f"| {item['source_id']} | `{item['mode']}` | `{item['preview_execution']}` | "
            f"{item['candidate_count']} | {item['accepted']} | {item['review_needed']} | "
            f"{item['exploratory']} | {item['rejected']} | `{item['recommended_next_action']}` |"
        )
    lines.extend(["", "## 可进入下一步的源", ""])
    ready = [item["source_id"] for item in report["sources"] if item["recommended_next_action"] == "raw_shadow_ingest_candidate"]
    if ready:
        lines.append("- raw shadow candidate: " + ", ".join(f"`{source}`" for source in ready))
    else:
        lines.append("- 当前没有源建议直接进入 raw shadow candidate。")
    manual = [item["source_id"] for item in report["sources"] if item["recommended_next_action"] == "needs_manual_review"]
    if manual:
        lines.append("- needs manual review: " + ", ".join(f"`{source}`" for source in manual))
    lines.extend(["", "## 安全边界", ""])
    for boundary in report["safety_boundaries"]:
        lines.append(f"- {boundary}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run offline four-source batch preview summary.")
    parser.add_argument("--plan-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "four_source_batch_plan_phase37.json"))
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--offline-only", action="store_true")
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "four_source_batch_preview_phase38.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "four_source_batch_preview_phase38.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    if args.batch_size <= 0:
        print("batch-size must be positive", file=sys.stderr)
        return 2

    report = build_preview(plan_path=Path(args.plan_json), batch_size=args.batch_size, offline_only=True)
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    print(
        f"sources={report['summary']['sources']} candidates={report['summary']['candidate_count']} "
        f"actions={report['summary']['recommended_actions']} active_source={ACTIVE_SOURCE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

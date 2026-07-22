from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sandbox_manifest_candidates import (
    SANDBOX_DIR,
    build_report,
    candidates_from_manifest,
    is_sandbox_path,
    load_manifest_from_path,
    write_json,
)


DEFAULT_JSON = SANDBOX_DIR / "candidate_review_summary.json"
DEFAULT_MD = SANDBOX_DIR / "candidate_review_summary.md"
VALID_REVIEW_DECISIONS = {"pending", "approved_for_small_batch", "needs_manifest_fix", "rejected"}


def manifest_paths(manifest_dir: Path) -> List[Path]:
    paths: List[Path] = []
    for path in sorted(path for path in Path(manifest_dir).glob("*.json") if path.is_file()):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            paths.append(path)
            continue
        if "source_name" not in payload and "candidate_sites" in payload:
            continue
        paths.append(path)
    return paths


def recommend(entry: Dict[str, Any]) -> str:
    triage = entry.get("triage_counts", {})
    candidate_count = int(entry.get("candidate_count", 0) or 0)
    accepted = int(triage.get("accepted", entry.get("accepted", 0)) or 0)
    rejected = int(triage.get("rejected", entry.get("rejected", 0)) or 0)
    if entry.get("source_mode") == "entity_data":
        return "source_specific_gate"
    if candidate_count == 0 or rejected > max(1, candidate_count // 2):
        return "needs_manifest_fix"
    if accepted > 0 and rejected <= accepted:
        return "ready_for_small_batch"
    return "manual_sample_first"


def review_decision(entry: Dict[str, Any]) -> Dict[str, Any]:
    recommendation = str(entry.get("recommendation") or "")
    if recommendation == "needs_manifest_fix":
        return {
            "review_decision": "needs_manifest_fix",
            "review_required": True,
            "sample_size_recommended": 0,
            "reviewer_notes_template": "修正 manifest include/exclude/domain 后重新生成 sandbox review。",
            "next_action": "fix manifest before any ingest trial",
        }
    if recommendation == "source_specific_gate":
        return {
            "review_decision": "pending",
            "review_required": True,
            "sample_size_recommended": "5-10",
            "reviewer_notes_template": "检查 machine/entity data 的专用字段、许可和 source-specific gate。",
            "next_action": "define source-specific review gate before ingest",
        }
    if recommendation == "ready_for_small_batch":
        return {
            "review_decision": "pending",
            "review_required": True,
            "sample_size_recommended": "10-20",
            "reviewer_notes_template": "人工确认 accepted/rejected samples 后再批准小批量抓取。",
            "next_action": "manual approve 10-20 samples before ingest",
        }
    return {
        "review_decision": "pending",
        "review_required": True,
        "sample_size_recommended": "5-10",
        "reviewer_notes_template": "人工抽样 review_needed/exploratory/rejected，确认是否调整 manifest。",
        "next_action": "manual sample 5-10 candidates before ingest",
    }


def review_template(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "sources": [
            {
                "source_id": item["source_id"],
                "review_decision": item["review_decision"],
                "reviewer_notes": "",
                "approved_sample_size": 0,
            }
            for item in report["items"]
        ],
    }


def load_review_decisions(path: Path) -> Dict[str, Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = payload.get("sources", []) if isinstance(payload, dict) else []
    decisions: Dict[str, Dict[str, Any]] = {}
    for item in sources:
        if not isinstance(item, dict):
            raise ValueError("review decision item must be an object")
        source_id = str(item.get("source_id") or "").strip()
        decision = str(item.get("review_decision") or "").strip()
        if decision not in VALID_REVIEW_DECISIONS:
            raise ValueError(f"invalid review_decision for {source_id}: {decision}")
        decisions[source_id] = item
    return decisions


def apply_review_decisions(report: Dict[str, Any], decisions: Dict[str, Dict[str, Any]]) -> None:
    items_by_source = {item["source_id"]: item for item in report["items"]}
    unknown = sorted(set(decisions) - set(items_by_source))
    if unknown:
        raise ValueError(f"unknown source_id in review decisions: {unknown}")
    for source_id, decision in decisions.items():
        item = items_by_source[source_id]
        review_value = str(decision.get("review_decision") or "").strip()
        notes = str(decision.get("reviewer_notes") or "")
        approved_size = int(decision.get("approved_sample_size", 0) or 0)
        item["review_decision"] = review_value
        item["reviewer_notes"] = notes
        item["approved_sample_size"] = approved_size
        if review_value == "approved_for_small_batch":
            item["review_required"] = False
            item["next_action"] = f"plan small-batch ingest for approved_sample_size={approved_size}; do not auto-run ingest"
        elif review_value == "needs_manifest_fix":
            item.update(review_decision({"recommendation": "needs_manifest_fix"}))
            item["reviewer_notes"] = notes
            item["approved_sample_size"] = approved_size
        elif review_value == "rejected":
            item["review_required"] = False
            item["sample_size_recommended"] = 0
            item["next_action"] = "do not ingest; keep source rejected in sandbox report"
        else:
            item.update(review_decision({"recommendation": item.get("recommendation")}))
            item["reviewer_notes"] = notes
            item["approved_sample_size"] = approved_size


def review_entry(manifest_path: Path, sandbox_dir: Path) -> Dict[str, Any]:
    manifest = load_manifest_from_path(manifest_path)
    candidates, skipped = candidates_from_manifest(manifest)
    report = build_report(manifest, manifest_path, candidates)
    report["frontier_skipped_count"] = len(skipped)
    report["frontier_skipped"] = skipped[:20]
    report["safety_flags"]["sandbox_report_only"] = True
    source_id = str(report["source_id"])
    per_source_path = Path(sandbox_dir) / f"{source_id}_sandbox_review.json"
    write_json(per_source_path, report)
    entry = {
        "source_id": source_id,
        "source_mode": manifest.get("source_mode", ""),
        "registered": report["registered"],
        "network": report["network"],
        "candidate_count": report["candidate_count"],
        "accepted": int(report["triage_counts"].get("accepted", 0) or 0),
        "review_needed": int(report["triage_counts"].get("review_needed", 0) or 0),
        "exploratory": int(report["triage_counts"].get("exploratory", 0) or 0),
        "rejected": int(report["triage_counts"].get("rejected", 0) or 0),
        "skipped": len(skipped),
        "top_reasons": report["top_reasons"],
        "manifest_validation": report["manifest_validation"],
        "sandbox_report": str(per_source_path),
        "reviewer_notes": "",
        "approved_sample_size": 0,
    }
    entry["recommendation"] = recommend(entry)
    entry.update(review_decision(entry))
    return entry


def build_summary(manifest_dir: Path, sandbox_dir: Path) -> Dict[str, Any]:
    items = [review_entry(path, sandbox_dir) for path in manifest_paths(manifest_dir)]
    recommendations = Counter(item["recommendation"] for item in items)
    return {
        "mode": "sandbox_candidate_review_summary",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_dir": str(manifest_dir),
        "sandbox_dir": str(sandbox_dir),
        "network": False,
        "summary": {
            "sources": len(items),
            "recommendation_counts": dict(sorted(recommendations.items())),
        },
        "items": items,
    }


def markdown_table(report: Dict[str, Any]) -> str:
    lines = [
        "# Sandbox Candidate Review",
        "",
        "未注册 Manifest 2.0 候选源的离线预审汇总；不联网，不写正式 raw/triples/Chroma/Neo4j。",
        "",
        "| source_id | mode | candidates | accepted | review | exploratory | rejected | skipped | recommendation |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["items"]:
        lines.append(
            "| {source_id} | {source_mode} | {candidate_count} | {accepted} | "
            "{review_needed} | {exploratory} | {rejected} | {skipped} | {recommendation} |".format(**item)
        )
    lines.extend([
        "",
        "## Manual Review Decisions",
        "",
        "| source_id | recommendation | review_decision | sample_size | approved_size | reviewer_notes | top reasons | next_action |",
        "|---|---|---|---:|---:|---|---|---|",
    ])
    for item in report["items"]:
        reasons = ", ".join(list(item.get("top_reasons", {}).keys())[:3])
        lines.append(
            "| {source_id} | {recommendation} | {review_decision} | {sample_size_recommended} | {approved_sample_size} | {reviewer_notes} | {reasons} | {next_action} |".format(
                reasons=reasons,
                **item,
            )
        )
    lines.extend([
        "",
        "## Candidate Samples",
        "",
    ])
    for item in report["items"]:
        lines.extend([
            f"### {item['source_id']}",
            "",
            "| title | url | triage | score | reasons |",
            "|---|---|---|---:|---|",
        ])
        sandbox_report = Path(str(item.get("sandbox_report") or ""))
        candidates = []
        if sandbox_report.exists():
            candidates = json.loads(sandbox_report.read_text(encoding="utf-8")).get("selected_candidate_snapshots", [])
        for candidate in candidates[:5]:
            reasons = ", ".join(candidate.get("reasons", [])[:3])
            lines.append(
                "| {title} | {url} | {triage} | {score} | {reasons} |".format(
                    title=str(candidate.get("title", "")).replace("|", "\\|"),
                    url=str(candidate.get("url", "")).replace("|", "\\|"),
                    triage=candidate.get("triage", ""),
                    score=candidate.get("score", ""),
                    reasons=reasons.replace("|", "\\|"),
                )
            )
        lines.append("")
    lines.extend([
        "",
        "## Recommendation Rules",
        "",
        "- `needs_manifest_fix`: 候选为空或 rejected 较多，先修 manifest / include-exclude。",
        "- `manual_sample_first`: 候选相关但证据不足，先人工抽样。",
        "- `ready_for_small_batch`: 有 accepted 且无硬风险，可进入小批量 trial。",
        "- `source_specific_gate`: 机器数据 / entity data 走专用 gate，不套普通网页规则。",
        "",
    ])
    return "\n".join(lines)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Summarize sandbox candidate reviews for Manifest 2.0 example sources.")
    parser.add_argument("--manifest-dir", default=str(ROOT / "configs" / "source_manifests" / "examples"))
    parser.add_argument("--sandbox-dir", default=str(SANDBOX_DIR))
    parser.add_argument("--out-json", default=str(DEFAULT_JSON))
    parser.add_argument("--out-md", default=str(DEFAULT_MD))
    parser.add_argument("--review-decisions", default="")
    parser.add_argument("--write-review-template", default="")
    args = parser.parse_args(argv)

    sandbox_dir = Path(args.sandbox_dir)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    review_template_path = Path(args.write_review_template) if args.write_review_template else None
    for path in (sandbox_dir, out_json, out_md, *([review_template_path] if review_template_path else [])):
        if not is_sandbox_path(path):
            print("outputs must stay under evaluation/source_quality/sandbox", file=sys.stderr)
            return 2
    report = build_summary(Path(args.manifest_dir), sandbox_dir)
    if args.review_decisions:
        try:
            apply_review_decisions(report, load_review_decisions(Path(args.review_decisions)))
        except ValueError as exc:
            print(f"review decision validation failed: {exc}", file=sys.stderr)
            return 2
    write_json(out_json, report)
    write_text(out_md, markdown_table(report))
    if review_template_path:
        write_json(review_template_path, review_template(report))
    print(f"sources={report['summary']['sources']} recommendations={report['summary']['recommendation_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

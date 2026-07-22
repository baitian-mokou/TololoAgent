from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


SOURCE_ID = "nasa"
APPROVED_DECISION = "approved_for_shadow_write"


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


def normalize(value: str) -> str:
    return " ".join(str(value or "").lower().strip().split())


def under_four_source_expansion(path: Path) -> bool:
    parts = list(path.resolve().parts)
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1))


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    parts = list(path.resolve().parts)
    if allow_docs and "docs" in parts:
        return True
    return under_four_source_expansion(path)


def repo_root_for_package(package_dir: Path) -> Path:
    parts = list(package_dir.resolve().parts)
    for index in range(len(parts) - 1):
        if parts[index : index + 2] == ["evaluation", "four_source_expansion"]:
            return Path(*parts[:index])
    return ROOT


def expected_shadow_dir(phase45_package_dir: Path) -> Path:
    return repo_root_for_package(phase45_package_dir) / "data" / "triples_shadow" / SOURCE_ID


def shadow_output_allowed(path: Path, phase45_package_dir: Path) -> bool:
    return path.resolve() == expected_shadow_dir(phase45_package_dir).resolve()


def package_payload(package_dir: Path) -> Dict[str, Any]:
    triples = read_json(package_dir / "triples_preview.json")
    narratives = read_json(package_dir / "narratives_preview.json")
    manifest = read_json(package_dir / "package_manifest.json")
    return {
        "triples": triples if isinstance(triples, list) else [],
        "narratives": narratives if isinstance(narratives, list) else [],
        "manifest": manifest if isinstance(manifest, dict) else {},
    }


def package_counts(package: Dict[str, Any]) -> Dict[str, int]:
    manifest = package.get("manifest", {})
    return {
        "items": int(manifest.get("items", 0) or 0),
        "triples": len(package.get("triples", [])),
        "narratives": len(package.get("narratives", [])),
    }


def approval_status(path: Path) -> Dict[str, Any]:
    approval = read_json(path)
    if not isinstance(approval, dict):
        approval = {}
    return {
        "source_id": str(approval.get("source_id") or ""),
        "approval_decision": str(approval.get("approval_decision") or ""),
        "approved_item_count": int(approval.get("approved_item_count", 0) or 0),
        "reviewer_notes": str(approval.get("reviewer_notes") or ""),
    }


def fingerprints(package: Dict[str, Any]) -> Dict[str, set[str]]:
    values = {"urls": set(), "titles": set(), "subjects": set()}
    for triple in package.get("triples", []):
        url = normalize(triple.get("source_url") or triple.get("object") or "")
        title = normalize(triple.get("source_title") or "")
        subject = normalize(triple.get("subject") or "")
        if url:
            values["urls"].add(url.rstrip("/"))
        if title:
            values["titles"].add(title)
        if subject:
            values["subjects"].add(subject)
    for narrative in package.get("narratives", []):
        url = normalize(narrative.get("source_url") or "")
        title = normalize(narrative.get("source_title") or narrative.get("page_title") or "")
        if url:
            values["urls"].add(url.rstrip("/"))
        if title:
            values["titles"].add(title)
    return values


def overlap_summary(first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, List[str]]:
    a = fingerprints(first)
    b = fingerprints(second)
    return {
        "urls": sorted(a["urls"] & b["urls"]),
        "titles": sorted(a["titles"] & b["titles"]),
        "subjects": sorted(a["subjects"] & b["subjects"]),
    }


def has_overlap(summary: Dict[str, Sequence[str]]) -> bool:
    return any(summary.get(key) for key in ("urls", "titles", "subjects"))


def combined_manifest(phase45_counts: Dict[str, int], phase52_counts: Dict[str, int]) -> Dict[str, Any]:
    return {
        "package": "nasa_combined_shadow_set_phase53",
        "source_id": SOURCE_ID,
        "generated_at": utc_now(),
        "items": phase45_counts["items"] + phase52_counts["items"],
        "triples": phase45_counts["triples"] + phase52_counts["triples"],
        "narratives": phase45_counts["narratives"] + phase52_counts["narratives"],
        "parts": [
            {"phase": "Phase 45", **phase45_counts},
            {"phase": "Phase 52", **phase52_counts},
        ],
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
    }


def retag_report(report: Dict[str, Any], phase: str) -> Dict[str, Any]:
    report["phase"] = phase
    return report


def blocked_report(
    reason: str,
    *,
    phase45_package_dir: Path,
    phase52_package_dir: Path,
    phase52_approval_path: Path,
    shadow_output_dir: Path,
    execute: bool,
    phase45_counts: Dict[str, int],
    phase52_counts: Dict[str, int],
    approval: Dict[str, Any],
    overlap: Dict[str, List[str]],
) -> Dict[str, Any]:
    expected = {
        "items": phase45_counts["items"] + phase52_counts["items"],
        "triples": phase45_counts["triples"] + phase52_counts["triples"],
        "narratives": phase45_counts["narratives"] + phase52_counts["narratives"],
    }
    return {
        "phase": "Phase 53",
        "mode": "nasa_shadow_combined_guarded_merge",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "allowed": False,
        "executed": False,
        "blocked_reason": reason,
        "execute_requested": bool(execute),
        "phase45_package_dir": str(phase45_package_dir),
        "phase52_package_dir": str(phase52_package_dir),
        "phase52_approval_path": str(phase52_approval_path),
        "shadow_output_dir": str(shadow_output_dir),
        "phase45_counts": phase45_counts,
        "phase52_counts": phase52_counts,
        "expected_combined_counts": expected,
        "combined_counts": expected,
        "approval": approval,
        "overlap_summary": overlap,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
    }


def write_combined(output_dir: Path, first: Dict[str, Any], second: Dict[str, Any], manifest: Dict[str, Any]) -> Dict[str, Any]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "triples_preview.json": first["triples"] + second["triples"],
        "narratives_preview.json": first["narratives"] + second["narratives"],
        "package_manifest.json": manifest,
    }
    written = []
    for name, payload in files.items():
        path = output_dir / name
        write_json(path, payload)
        written.append(str(path))
    return {"files_written": written, "file_count": len(written)}


def build_merge_report(
    *,
    phase45_package_dir: Path,
    phase52_package_dir: Path,
    phase52_approval_path: Path,
    shadow_output_dir: Path,
    execute: bool = False,
    report_phase: str = "Phase 53",
) -> Dict[str, Any]:
    phase45 = package_payload(phase45_package_dir)
    phase52 = package_payload(phase52_package_dir)
    phase45_counts = package_counts(phase45)
    phase52_counts = package_counts(phase52)
    approval = approval_status(phase52_approval_path)
    overlap = overlap_summary(phase45, phase52)
    common = {
        "phase45_package_dir": phase45_package_dir,
        "phase52_package_dir": phase52_package_dir,
        "phase52_approval_path": phase52_approval_path,
        "shadow_output_dir": shadow_output_dir,
        "execute": execute,
        "phase45_counts": phase45_counts,
        "phase52_counts": phase52_counts,
        "approval": approval,
        "overlap": overlap,
    }
    if approval["source_id"] != SOURCE_ID:
        return retag_report(blocked_report("approval_source_mismatch", **common), report_phase)
    if approval["approval_decision"] != APPROVED_DECISION:
        return retag_report(blocked_report("approval_not_approved", **common), report_phase)
    if approval["approved_item_count"] != phase52_counts["items"] or phase52_counts["items"] <= 0:
        return retag_report(blocked_report("approved_item_count_mismatch", **common), report_phase)
    if not shadow_output_allowed(shadow_output_dir, phase45_package_dir):
        return retag_report(blocked_report("output_not_fixed_shadow_path", **common), report_phase)
    if has_overlap(overlap):
        return retag_report(blocked_report("package_overlap_detected", **common), report_phase)
    if min(phase45_counts.values()) <= 0 or min(phase52_counts.values()) <= 0:
        return retag_report(blocked_report("package_missing_records", **common), report_phase)

    manifest = combined_manifest(phase45_counts, phase52_counts)
    copy_result = write_combined(shadow_output_dir, phase45, phase52, manifest) if execute else {"files_written": [], "file_count": 0}
    expected = {"items": manifest["items"], "triples": manifest["triples"], "narratives": manifest["narratives"]}
    return {
        "phase": report_phase,
        "mode": "nasa_shadow_combined_guarded_merge",
        "generated_at": manifest["generated_at"],
        "source_id": SOURCE_ID,
        "allowed": True,
        "executed": bool(execute),
        "blocked_reason": "",
        "execute_requested": bool(execute),
        "phase45_package_dir": str(phase45_package_dir),
        "phase52_package_dir": str(phase52_package_dir),
        "phase52_approval_path": str(phase52_approval_path),
        "shadow_output_dir": str(shadow_output_dir),
        "phase45_counts": phase45_counts,
        "phase52_counts": phase52_counts,
        "expected_combined_counts": expected,
        "combined_counts": expected,
        "approval": approval,
        "overlap_summary": overlap,
        "copy_result": copy_result,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# NASA combined shadow merge guard preflight",
        "",
        f"{report['phase']} validates merging a base NASA shadow package with the next pending package. The default path is preflight only; pending approval blocks execution.",
        "",
        f"- allowed: `{report['allowed']}`",
        f"- executed: `{report['executed']}`",
        f"- blocked_reason: `{report['blocked_reason']}`",
        f"- phase45_items: `{report['phase45_counts']['items']}`",
        f"- phase52_items: `{report['phase52_counts']['items']}`",
        f"- expected_combined_items: `{report['expected_combined_counts']['items']}`",
        f"- expected_combined_triples: `{report['expected_combined_counts']['triples']}`",
        f"- expected_combined_narratives: `{report['expected_combined_counts']['narratives']}`",
        f"- approval_decision: `{report['approval'].get('approval_decision')}`",
        f"- approved_item_count: `{report['approval'].get('approved_item_count')}`",
        "",
        "## Overlap Check",
        "",
        f"- urls: `{len(report['overlap_summary']['urls'])}`",
        f"- titles: `{len(report['overlap_summary']['titles'])}`",
        f"- subjects: `{len(report['overlap_summary']['subjects'])}`",
        "",
        "## Safety",
        "",
    ]
    for key in ("formal_default_triples_write", "chroma_write", "neo4j_write", "active_source_unchanged"):
        lines.append(f"- {key}: `{report[key]}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Guarded merge of NASA Phase 45 and Phase 52 shadow packages.")
    parser.add_argument("--phase45-package-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_limited_shadow_package_phase45"))
    parser.add_argument("--phase52-package-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_second_shadow_package_phase52"))
    parser.add_argument("--phase52-approval", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_second_shadow_package_approval_phase52.json"))
    parser.add_argument("--base-package-dir")
    parser.add_argument("--next-package-dir")
    parser.add_argument("--next-approval")
    parser.add_argument("--report-phase", default="Phase 53")
    parser.add_argument("--shadow-output-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument("--report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_combined_merge_preflight_phase53.json"))
    parser.add_argument("--report-md", default=str(ROOT / "docs" / "nasa_shadow_combined_merge_preflight_phase53.md"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    report_json = Path(args.report_json)
    report_md = Path(args.report_md)
    if not output_allowed(report_json) or not output_allowed(report_md, allow_docs=True):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2

    report = build_merge_report(
        phase45_package_dir=Path(args.base_package_dir or args.phase45_package_dir),
        phase52_package_dir=Path(args.next_package_dir or args.phase52_package_dir),
        phase52_approval_path=Path(args.next_approval or args.phase52_approval),
        shadow_output_dir=Path(args.shadow_output_dir),
        execute=bool(args.execute),
        report_phase=args.report_phase,
    )
    write_json(report_json, report)
    write_text(report_md, render_markdown(report))
    print(
        f"allowed={report['allowed']} executed={report['executed']} blocked={report['blocked_reason']} "
        f"combined_items={report['expected_combined_counts']['items']} active_source={ACTIVE_SOURCE}"
    )
    return 0 if report["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

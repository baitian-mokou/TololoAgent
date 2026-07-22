from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


SOURCE_ID = "esa"
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


def under_four_source_expansion(path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return relative.parts[:2] == ("evaluation", "four_source_expansion")


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return relative.parts[:2] == ("evaluation", "four_source_expansion") or (allow_docs and relative.parts[:1] == ("docs",))


def repo_root_for_package(package_dir: Path) -> Path:
    resolved = package_dir.resolve()
    parts = list(resolved.parts)
    for index in range(len(parts) - 1):
        if parts[index : index + 2] == ["evaluation", "four_source_expansion"]:
            return Path(*parts[:index])
    return ROOT


def expected_shadow_output_dir(package_dir: Path) -> Path:
    return repo_root_for_package(package_dir) / "data" / "triples_shadow" / SOURCE_ID


def shadow_output_allowed(path: Path, package_dir: Path) -> bool:
    return path.resolve() == expected_shadow_output_dir(package_dir).resolve()


def package_counts(package_dir: Path) -> Dict[str, int]:
    triples = read_json(package_dir / "triples_preview.json")
    narratives = read_json(package_dir / "narratives_preview.json")
    manifest = read_json(package_dir / "package_manifest.json")
    return {
        "items": int(manifest.get("items", 0) or 0) if isinstance(manifest, dict) else 0,
        "triples": len(triples) if isinstance(triples, list) else 0,
        "narratives": len(narratives) if isinstance(narratives, list) else 0,
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


def copy_package_preview(package_dir: Path, output_dir: Path) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name in ("triples_preview.json", "narratives_preview.json", "package_manifest.json"):
        src = package_dir / name
        if src.exists():
            dst = output_dir / name
            shutil.copyfile(src, dst)
            written.append(str(dst))
    return {"files_written": written, "file_count": len(written)}


def base_report(reason: str, package_dir: Path, approval_path: Path, shadow_output_dir: Path, execute: bool) -> Dict[str, Any]:
    return {
        "phase": "Phase 70",
        "mode": "guarded_esa_shadow_apply_preflight",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "allowed": False,
        "executed": False,
        "blocked_reason": reason,
        "package_dir": str(package_dir),
        "approval_path": str(approval_path),
        "shadow_output_dir": str(shadow_output_dir),
        "execute_requested": execute,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
    }


def build_apply_report(*, package_dir: Path, approval_path: Path, shadow_output_dir: Path, execute: bool = False) -> Dict[str, Any]:
    approval = approval_status(approval_path)
    counts = package_counts(package_dir)
    if approval["source_id"] != SOURCE_ID:
        report = base_report("approval_source_mismatch", package_dir, approval_path, shadow_output_dir, execute)
    elif approval["approval_decision"] != APPROVED_DECISION:
        report = base_report("approval_not_approved", package_dir, approval_path, shadow_output_dir, execute)
    elif approval["approved_item_count"] != counts["items"] or counts["items"] <= 0:
        report = base_report("approved_item_count_mismatch", package_dir, approval_path, shadow_output_dir, execute)
    elif not shadow_output_allowed(shadow_output_dir, package_dir):
        report = base_report("output_not_shadow_only", package_dir, approval_path, shadow_output_dir, execute)
    elif counts["triples"] <= 0 or counts["narratives"] <= 0:
        report = base_report("package_missing_preview_records", package_dir, approval_path, shadow_output_dir, execute)
    else:
        report = {
            **base_report("", package_dir, approval_path, shadow_output_dir, execute),
            "allowed": True,
            "executed": bool(execute),
            "copy_result": copy_package_preview(package_dir, shadow_output_dir) if execute else {"files_written": [], "file_count": 0},
        }
    report["approval"] = approval
    report["package_counts"] = counts
    return report


def render_md(report: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# ESA guarded shadow apply preflight",
            "",
            f"- allowed: `{report['allowed']}`",
            f"- executed: `{report['executed']}`",
            f"- blocked_reason: `{report['blocked_reason']}`",
            f"- items: `{report['package_counts']['items']}`",
            f"- triples: `{report['package_counts']['triples']}`",
            f"- narratives: `{report['package_counts']['narratives']}`",
            f"- shadow_output_dir: `{report['shadow_output_dir']}`",
            f"- chroma_write: `{report['chroma_write']}`",
            f"- neo4j_write: `{report['neo4j_write']}`",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guarded ESA shadow package apply. Defaults to preflight refusal while approval is pending.")
    parser.add_argument("--package-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_shadow_package_phase69"))
    parser.add_argument("--approval", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_shadow_package_approval_phase69.json"))
    parser.add_argument("--shadow-output-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument("--report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "esa_shadow_apply_preflight_phase70.json"))
    parser.add_argument("--report-md", default=str(ROOT / "docs" / "esa_shadow_apply_preflight_phase70.md"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    report_json = Path(args.report_json)
    report_md = Path(args.report_md)
    if not output_allowed(report_json) or not output_allowed(report_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = build_apply_report(package_dir=Path(args.package_dir), approval_path=Path(args.approval), shadow_output_dir=Path(args.shadow_output_dir), execute=bool(args.execute))
    write_json(report_json, report)
    write_text(report_md, render_md(report))
    print(f"allowed={report['allowed']} executed={report['executed']} blocked={report['blocked_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

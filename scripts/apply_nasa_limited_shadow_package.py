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


def under_evaluation(path: Path) -> bool:
    parts = list(path.resolve().parts)
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1))


def shadow_output_allowed(path: Path) -> bool:
    resolved = path.resolve()
    parts = [part.lower() for part in resolved.parts]
    joined = "/".join(parts)
    if "shadow" not in joined:
        return False
    forbidden_suffixes = [
        ("data", "triples"),
        ("data", "triples", SOURCE_ID),
    ]
    for suffix in forbidden_suffixes:
        if tuple(parts[-len(suffix) :]) == suffix:
            return False
    return True


def report_output_allowed(path: Path) -> bool:
    return under_evaluation(path)


def package_counts(package_dir: Path) -> Dict[str, int]:
    triples = read_json(package_dir / "triples_preview.json")
    narratives = read_json(package_dir / "narratives_preview.json")
    return {
        "triples": len(triples) if isinstance(triples, list) else 0,
        "narratives": len(narratives) if isinstance(narratives, list) else 0,
    }


def approval_status(approval_path: Path) -> Dict[str, Any]:
    approval = read_json(approval_path)
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


def blocked_report(reason: str, package_dir: Path, approval_path: Path, shadow_output_dir: Path, execute: bool) -> Dict[str, Any]:
    return {
        "phase": "Phase 46 readiness",
        "mode": "guarded_nasa_limited_shadow_apply",
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
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
    }


def build_apply_report(
    *,
    package_dir: Path,
    approval_path: Path,
    shadow_output_dir: Path,
    execute: bool = False,
) -> Dict[str, Any]:
    approval = approval_status(approval_path)
    counts = package_counts(package_dir)
    if approval["source_id"] != SOURCE_ID:
        report = blocked_report("approval_source_mismatch", package_dir, approval_path, shadow_output_dir, execute)
    elif approval["approval_decision"] != APPROVED_DECISION:
        report = blocked_report("approval_not_approved", package_dir, approval_path, shadow_output_dir, execute)
    elif approval["approved_item_count"] <= 0:
        report = blocked_report("approved_item_count_not_positive", package_dir, approval_path, shadow_output_dir, execute)
    elif not shadow_output_allowed(shadow_output_dir):
        report = blocked_report("output_not_shadow_only", package_dir, approval_path, shadow_output_dir, execute)
    elif counts["triples"] <= 0 or counts["narratives"] <= 0:
        report = blocked_report("package_missing_preview_records", package_dir, approval_path, shadow_output_dir, execute)
    else:
        copy_result = copy_package_preview(package_dir, shadow_output_dir) if execute else {"files_written": [], "file_count": 0}
        report = {
            "phase": "Phase 46 readiness",
            "mode": "guarded_nasa_limited_shadow_apply",
            "generated_at": utc_now(),
            "source_id": SOURCE_ID,
            "allowed": True,
            "executed": bool(execute),
            "blocked_reason": "",
            "package_dir": str(package_dir),
            "approval_path": str(approval_path),
            "shadow_output_dir": str(shadow_output_dir),
            "approval": approval,
            "package_counts": counts,
            "copy_result": copy_result,
            "formal_default_triples_write": False,
            "chroma_write": False,
            "neo4j_write": False,
            "active_source": ACTIVE_SOURCE,
            "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
            "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        }
    report["approval"] = approval
    report["package_counts"] = counts
    return report


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Guarded NASA limited shadow package apply. Refuses unless approval is explicit.")
    parser.add_argument("--package-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_limited_shadow_package_phase45"))
    parser.add_argument("--approval", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_limited_shadow_package_approval_phase45.json"))
    parser.add_argument("--shadow-output-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument("--report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_limited_shadow_apply_guard_phase46.json"))
    parser.add_argument("--execute", action="store_true", help="Copy package preview files to the approved shadow-only output directory.")
    args = parser.parse_args(argv)

    report_path = Path(args.report_json)
    if not report_output_allowed(report_path):
        print("report-json must stay under evaluation/four_source_expansion/", file=sys.stderr)
        return 2
    report = build_apply_report(
        package_dir=Path(args.package_dir),
        approval_path=Path(args.approval),
        shadow_output_dir=Path(args.shadow_output_dir),
        execute=bool(args.execute),
    )
    write_json(report_path, report)
    print(
        f"allowed={report['allowed']} executed={report['executed']} blocked={report['blocked_reason']} "
        f"active_source={ACTIVE_SOURCE}"
    )
    return 0 if report["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


SOURCE_ID = "nasa"
EXPECTED = {"items": 48, "triples": 192, "narratives": 192}
REQUIRED_FILES = ("triples_preview.json", "narratives_preview.json", "package_manifest.json")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    parts = list(path.resolve().parts)
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1)) or (
        allow_docs and "docs" in parts
    )


def rebuild_command() -> str:
    return (
        "python scripts\\merge_nasa_shadow_packages.py "
        "--report-phase \"Phase 62\" "
        "--base-package-dir data\\triples_shadow\\nasa "
        "--next-package-dir evaluation\\four_source_expansion\\nasa_fourth_shadow_package_phase60 "
        "--next-approval evaluation\\four_source_expansion\\nasa_fourth_shadow_package_approval_phase60.json "
        "--shadow-output-dir data\\triples_shadow\\nasa "
        "--report-json evaluation\\four_source_expansion\\nasa_shadow_combined_merge_apply_phase62.json "
        "--report-md docs\\nasa_shadow_combined_merge_apply_phase62.md --execute"
    )


def base_report(shadow_dir: Path, phase: str = "Phase 56") -> Dict[str, Any]:
    return {
        "phase": phase,
        "mode": "nasa_shadow_combined_artifact_verification",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_id": SOURCE_ID,
        "shadow_dir": str(shadow_dir),
        "local_artifact": True,
        "rebuild_command": rebuild_command(),
        "active_source": ACTIVE_SOURCE,
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
    }


def triple_key(row: Dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(row.get(k, "")).strip().lower() for k in ("subject", "predicate", "object", "source_url"))


def verify_artifact(
    shadow_dir: Path,
    *,
    phase: str = "Phase 56",
    expected_items: int = EXPECTED["items"],
    expected_triples: int = EXPECTED["triples"],
    expected_narratives: int = EXPECTED["narratives"],
) -> Dict[str, Any]:
    report = base_report(shadow_dir, phase)
    present = sorted(p.name for p in shadow_dir.glob("*") if p.is_file()) if shadow_dir.exists() else []
    missing = [name for name in REQUIRED_FILES if name not in present]
    extra = [name for name in present if name not in REQUIRED_FILES]
    if missing or extra:
        return {**report, "ready": False, "blocked_reason": "missing_shadow_files" if missing else "unexpected_shadow_files", "files": present, "missing_files": missing, "extra_files": extra}

    triples = read_json(shadow_dir / "triples_preview.json")
    narratives = read_json(shadow_dir / "narratives_preview.json")
    manifest = read_json(shadow_dir / "package_manifest.json")
    if not isinstance(triples, list) or not isinstance(narratives, list) or not isinstance(manifest, dict):
        return {**report, "ready": False, "blocked_reason": "invalid_shadow_json", "files": present}

    counts = {"items": int(manifest.get("items", 0) or 0), "triples": len(triples), "narratives": len(narratives)}
    manifest_counts = {k: int(manifest.get(k, 0) or 0) for k in ("items", "triples", "narratives")}
    expected = {"items": expected_items, "triples": expected_triples, "narratives": expected_narratives}
    duplicate_triples = len(triples) - len({triple_key(row) for row in triples if isinstance(row, dict)})
    validation = {
        "triple_source_ids": dict(Counter(str(row.get("source_id", "")) for row in triples if isinstance(row, dict))),
        "triple_validation_status": dict(Counter(str(row.get("validation_status", "")) for row in triples if isinstance(row, dict))),
        "narrative_source_ids": dict(Counter(str(row.get("source_id", "")) for row in narratives if isinstance(row, dict))),
        "narrative_source_roles": dict(Counter(str(row.get("source_role", "")) for row in narratives if isinstance(row, dict))),
        "duplicate_triples": duplicate_triples,
    }
    issues = []
    if counts != expected or manifest_counts != expected:
        issues.append("count_mismatch")
    if duplicate_triples:
        issues.append("duplicate_triples")
    if validation["triple_source_ids"] != {SOURCE_ID: len(triples)}:
        issues.append("triple_source_id_mismatch")
    if validation["triple_validation_status"] != {"accepted": len(triples)}:
        issues.append("triple_validation_status_mismatch")
    if validation["narrative_source_ids"] != {SOURCE_ID: len(narratives)}:
        issues.append("narrative_source_id_mismatch")
    if validation["narrative_source_roles"] != {"primary": len(narratives)}:
        issues.append("narrative_source_role_mismatch")

    return {
        **report,
        "ready": not issues,
        "blocked_reason": issues[0] if issues else "",
        "issues": issues,
        "files": present,
        "counts": counts,
        "manifest_counts": manifest_counts,
        "expected_counts": expected,
        "overlap_summary": {"urls": [], "titles": [], "subjects": []},
        "validation": validation,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# NASA combined shadow artifact verification",
            "",
            f"- ready: `{report.get('ready')}`",
            f"- blocked_reason: `{report.get('blocked_reason', '')}`",
            f"- counts: `{report.get('counts', {})}`",
            f"- expected_counts: `{report.get('expected_counts', EXPECTED)}`",
            f"- duplicate_triples: `{report.get('validation', {}).get('duplicate_triples', 0)}`",
            f"- rebuild_command: `{report.get('rebuild_command')}`",
            f"- formal_default_triples_write: `{report.get('formal_default_triples_write')}`",
            f"- chroma_write: `{report.get('chroma_write')}`",
            f"- neo4j_write: `{report.get('neo4j_write')}`",
            f"- active_source_unchanged: `{report.get('active_source_unchanged')}`",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify local NASA combined shadow artifact.")
    parser.add_argument("--shadow-dir", default=str(ROOT / "data" / "triples_shadow" / SOURCE_ID))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_combined_artifact_verification_phase56.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_shadow_combined_artifact_verification_phase56.md"))
    parser.add_argument("--phase", default="Phase 56")
    parser.add_argument("--expected-items", type=int, default=EXPECTED["items"])
    parser.add_argument("--expected-triples", type=int, default=EXPECTED["triples"])
    parser.add_argument("--expected-narratives", type=int, default=EXPECTED["narratives"])
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    report = verify_artifact(
        Path(args.shadow_dir),
        phase=args.phase,
        expected_items=args.expected_items,
        expected_triples=args.expected_triples,
        expected_narratives=args.expected_narratives,
    )
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    print(f"ready={report['ready']} blocked={report['blocked_reason']} counts={report.get('counts', {})} active_source={ACTIVE_SOURCE}")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

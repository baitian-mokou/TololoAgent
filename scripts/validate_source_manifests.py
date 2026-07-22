from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "configs" / "source_manifests"
DEFAULT_REPORT = ROOT / "evaluation" / "source_quality" / "source_manifest_validation_report.json"
VALID_SOURCE_MODES = {"official_science", "academic", "publisher", "generic_unknown", "entity_data"}
REQUIRED_FIELDS = (
    "source_name",
    "source_mode",
    "allowed_domains",
    "include_path_keywords",
    "exclude_path_keywords",
    "topic_taxonomy",
    "quality_gate",
    "quality_notes",
)
QUALITY_GATE_FIELDS = ("accepted_min_score", "review_min_score", "allow_exploratory", "skip_rejected_allowed")


def read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def int_in_range(value: Any) -> bool:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False
    return 0 <= number <= 100


def validate_manifest(manifest: Dict[str, Any], path: Path) -> List[str]:
    errors: List[str] = []
    for field in REQUIRED_FIELDS:
        if field not in manifest:
            errors.append(f"missing {field}")
    if not manifest.get("seed_urls") and not manifest.get("seed_entities"):
        errors.append("missing seed_urls or seed_entities")
    source_mode = str(manifest.get("source_mode") or "")
    if source_mode not in VALID_SOURCE_MODES:
        errors.append(f"invalid source_mode: {source_mode}")
    for list_field in ("allowed_domains", "include_path_keywords", "exclude_path_keywords", "topic_taxonomy"):
        if list_field in manifest and not isinstance(manifest.get(list_field), list):
            errors.append(f"{list_field} must be a list")
    gate = manifest.get("quality_gate") if isinstance(manifest.get("quality_gate"), dict) else {}
    if not gate:
        errors.append("quality_gate must be an object")
    for field in QUALITY_GATE_FIELDS:
        if field not in gate:
            errors.append(f"missing quality_gate.{field}")
    for field in ("accepted_min_score", "review_min_score"):
        if field in gate and not int_in_range(gate.get(field)):
            errors.append(f"quality_gate.{field} must be 0..100")
    if gate and int(gate.get("review_min_score", 0) or 0) > int(gate.get("accepted_min_score", 100) or 100):
        errors.append("quality_gate.review_min_score cannot exceed accepted_min_score")
    for field in ("allow_exploratory", "skip_rejected_allowed"):
        if field in gate and not isinstance(gate.get(field), bool):
            errors.append(f"quality_gate.{field} must be boolean")
    if source_mode == "entity_data" and gate.get("skip_rejected_allowed") is True:
        errors.append("entity_data cannot set skip_rejected_allowed true")
    if str(manifest.get("source_name") or "") != path.stem and path.parent.name != "examples":
        errors.append("source_name must match filename")
    return errors


def manifest_paths(manifest_dir: Path) -> List[Path]:
    paths: List[Path] = []
    for path in sorted(path for path in manifest_dir.rglob("*.json") if path.is_file()):
        try:
            payload = read_json(path)
        except Exception:
            paths.append(path)
            continue
        if "source_name" not in payload and "candidate_sites" in payload:
            continue
        paths.append(path)
    return paths


def validate_manifest_tree(manifest_dir: Path = MANIFEST_DIR) -> Dict[str, Any]:
    items = []
    failed = 0
    for path in manifest_paths(Path(manifest_dir)):
        try:
            manifest = read_json(path)
            errors = validate_manifest(manifest, path)
        except Exception as exc:
            manifest = {}
            errors = [f"{type(exc).__name__}: {exc}"]
        failed += 1 if errors else 0
        items.append({
            "path": str(path),
            "source_name": manifest.get("source_name", path.stem),
            "source_mode": manifest.get("source_mode", ""),
            "passed": not errors,
            "errors": errors,
        })
    return {
        "passed": failed == 0,
        "summary": {"validated": len(items), "failed": failed},
        "items": items,
    }


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Validate source manifest 2.0 fields.")
    parser.add_argument("--manifest-dir", default=str(MANIFEST_DIR))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT))
    args = parser.parse_args(argv)

    report = validate_manifest_tree(Path(args.manifest_dir))
    write_json(Path(args.report_json), report)
    print(f"validated={report['summary']['validated']} failed={report['summary']['failed']} passed={report['passed']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

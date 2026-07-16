from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import BASE_DIR


RAW_ROOT = os.path.join(BASE_DIR, "data", "raw_json")
TRIPLES_ROOT = os.path.join(BASE_DIR, "data", "triples")
EVALUATION_ROOT = os.path.join(BASE_DIR, "evaluation", "ingestion")
IGNORED_RAW_FILENAMES = {"__crawl_state__.json", "solar_system_fixture.json", "smoke_fixture.json", "discovery_fixture.json"}


def _parse_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_file_timestamp(paths: Sequence[Path]) -> datetime | None:
    latest = None
    for path in paths:
        if not path.exists():
            continue
        current = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if latest is None or current > latest:
            latest = current
    return latest


def _raw_files_for_source(source_name: str, raw_root: str) -> List[Path]:
    raw_dir = Path(raw_root) / source_name
    if not raw_dir.exists():
        return []
    return [
        path for path in sorted(raw_dir.glob("*.json"))
        if path.name not in IGNORED_RAW_FILENAMES
    ]


def _triple_output_files_for_source(source_name: str, triples_root: str) -> List[Path]:
    triples_dir = Path(triples_root) / source_name
    if not triples_dir.exists():
        return []
    return [path for path in sorted(triples_dir.glob("*.json")) if path.name != "summary.json"]


def validate_ingestion_outputs(
    sources: Sequence[str],
    *,
    raw_root: str = RAW_ROOT,
    triples_root: str = TRIPLES_ROOT,
    evaluation_root: str = EVALUATION_ROOT,
) -> Dict[str, Any]:
    source_checks: List[Dict[str, Any]] = []
    incomplete_sources: List[str] = []

    for source_name in sources:
        issues: List[str] = []
        raw_dir = Path(raw_root) / source_name
        triples_dir = Path(triples_root) / source_name
        report_path = Path(evaluation_root) / f"{source_name}_ingestion_report.json"

        raw_files = _raw_files_for_source(source_name, raw_root)
        triple_files = _triple_output_files_for_source(source_name, triples_root)

        if not raw_dir.exists():
            issues.append("missing_raw_dir")
        if raw_dir.exists() and not raw_files:
            issues.append("raw_dir_has_no_records")
        if not triples_dir.exists():
            issues.append("missing_triples_dir")
        if triples_dir.exists() and not triple_files:
            issues.append("triples_dir_has_no_outputs")
        if not report_path.exists():
            issues.append("missing_ingestion_report")

        report_generated_at = None
        latest_output_at = _latest_file_timestamp(raw_files + triple_files)
        if report_path.exists():
            try:
                report_payload = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                report_payload = {}
                issues.append("invalid_ingestion_report")
            report_generated_at = _parse_timestamp(report_payload.get("generated_at", ""))
            if report_generated_at is None:
                issues.append("missing_or_invalid_generated_at")
            elif latest_output_at and report_generated_at < latest_output_at:
                issues.append("stale_ingestion_report")

        if issues:
            incomplete_sources.append(source_name)

        source_checks.append(
            {
                "source": source_name,
                "raw_dir": str(raw_dir),
                "triples_dir": str(triples_dir),
                "report_path": str(report_path),
                "raw_record_count": len(raw_files),
                "triple_output_count": len(triple_files),
                "latest_output_at": latest_output_at.isoformat() if latest_output_at else "",
                "report_generated_at": report_generated_at.isoformat() if report_generated_at else "",
                "issues": issues,
            }
        )

    return {
        "sources": list(sources),
        "passed": not bool(incomplete_sources),
        "incomplete_sources": incomplete_sources,
        "source_checks": source_checks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Validate controlled ingestion outputs without mutating the workspace.")
    parser.add_argument("--sources", nargs="+", required=True)
    args = parser.parse_args()

    report = validate_ingestion_outputs(args.sources)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())

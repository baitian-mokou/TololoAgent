from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.build_four_source_shadow_normalize_preview_phase83 import normalize


SCHEMA_VERSION = "phase86_nasa_metadata_repair_preview_v1"


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


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return rel.parts[:3] == ("evaluation", "four_source_expansion", "phase86") or (allow_docs and rel.parts[:1] == ("docs",))


def title_from_excerpt(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return ""
    head = text.split(" Explore ", 1)[0].split(" Search ", 1)[0].strip()
    head = re.sub(r"\s*-\s*NASA(?: Science)?$", "", head).strip()
    return head[:120]


def nasa_succeeded_rows(phase82: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = phase82.get("raw_previews", []) if isinstance(phase82.get("raw_previews"), list) else []
    return [row for row in rows if row.get("source") == "nasa" and row.get("fetched") is True and row.get("status") != "failed"]


def nasa_rejected_rows(phase83: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = phase83.get("rejected_records", []) if isinstance(phase83.get("rejected_records"), list) else []
    return [row for row in rows if row.get("source") == "nasa"]


def repair_row(row: Dict[str, Any]) -> tuple[Dict[str, Any] | None, str]:
    url = str(row.get("url") or "").strip()
    title = str(row.get("title") or "").strip() or title_from_excerpt(str(row.get("text_excerpt") or ""))
    if not url:
        return None, "missing_source_url"
    if not title:
        return None, "missing_title_signal"
    repaired = {
        "source": "nasa",
        "source_id": "nasa",
        "title": title,
        "id": title,
        "url": url,
        "source_url": url,
        "entity_id": "",
        "schema_version": SCHEMA_VERSION,
        "repair_reason": "phase82_succeeded_missing_title_metadata",
        "reason": row.get("reason", ""),
        "fetched": True,
        "status": "metadata_repaired_preview",
        "text_excerpt": row.get("text_excerpt", ""),
        "quality_flags": {**(row.get("quality_flags") if isinstance(row.get("quality_flags"), dict) else {}), "metadata_repaired": True},
        "provenance": {"phase82_status": row.get("status", ""), "phase82_url": url, "phase86_rule": "title_from_existing_excerpt_or_existing_title"},
    }
    normalized, reason = normalize(repaired)
    if normalized is None:
        return None, reason
    return repaired, ""


def build_report(*, phase82_report: Path, phase83_report: Path, root: Path = ROOT) -> Dict[str, Any]:
    phase82 = read_json(phase82_report)
    phase83 = read_json(phase83_report)
    succeeded = nasa_succeeded_rows(phase82 if isinstance(phase82, dict) else {})
    rejected = nasa_rejected_rows(phase83 if isinstance(phase83, dict) else {})
    repaired: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for row in succeeded:
        item, reason = repair_row(row)
        if item is None:
            failures.append({"url": row.get("url", ""), "reason": reason})
        else:
            repaired.append(item)
    return {
        "phase": "Phase 86",
        "mode": "nasa_metadata_repair_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root_cause": "Phase82 NASA preview rows had URL/text but blank title/id, so Phase83 rejected them as missing_source_metadata.",
        "repair_rules": ["only Phase82 NASA fetched rows", "no live fetch", "derive title from existing title or text_excerpt heading", "require URL and title", "rerun Phase83 normalize gate"],
        "phase82_nasa_succeeded": len(succeeded),
        "phase83_nasa_rejected": len(rejected),
        "nasa_succeeded_phase82": len(succeeded),
        "repaired_count": len(repaired),
        "passed_normalize_gate": len(repaired),
        "remaining_failures": len(failures),
        "repaired_candidates": repaired,
        "remaining_failure_records": failures,
        "sufficient_to_rebuild_pending_package": bool(repaired),
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "clear_source_ingestion_outputs_called": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {s: SOURCE_REGISTRY.get(s, "unknown") for s in ("zh_wikipedia", "nasa", "esa", "wikidata")},
    }


def render_md(report: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# NASA metadata repair preview",
            "",
            f"- phase82_nasa_succeeded: `{report['phase82_nasa_succeeded']}`",
            f"- phase83_nasa_rejected: `{report['phase83_nasa_rejected']}`",
            f"- repaired_count: `{report['repaired_count']}`",
            f"- passed_normalize_gate: `{report['passed_normalize_gate']}`",
            f"- remaining_failures: `{report['remaining_failures']}`",
            f"- sufficient_to_rebuild_pending_package: `{report['sufficient_to_rebuild_pending_package']}`",
            "",
            "No live fetch, no formal writes, and NASA remains disabled/shadow.",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair NASA metadata from Phase82/83 previews only.")
    parser.add_argument("--phase82-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase82" / "four_source_controlled_raw_preview_phase82.json"))
    parser.add_argument("--phase83-report", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase83" / "four_source_shadow_normalize_preview_phase83.json"))
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "phase86" / "nasa_metadata_repair_preview_phase86.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "nasa_metadata_repair_preview_phase86.md"))
    args = parser.parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md, allow_docs=True):
        print("outputs must stay under repo evaluation/four_source_expansion/phase86 or docs/", file=sys.stderr)
        return 2
    report = build_report(phase82_report=Path(args.phase82_report), phase83_report=Path(args.phase83_report))
    write_json(out_json, report)
    write_text(out_md, render_md(report))
    print(f"repaired={report['repaired_count']} pass={report['passed_normalize_gate']} fail={report['remaining_failures']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

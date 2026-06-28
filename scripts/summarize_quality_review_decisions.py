from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, BASE_DIR, SOURCE_REGISTRY


DEFAULT_DECISIONS = Path(BASE_DIR) / "data" / "quality_review" / "quality_review_decisions.json"
DEFAULT_OUTPUT = Path(BASE_DIR) / "evaluation" / "quality_review_decision_summary.json"
ALLOWED_DECISIONS = ("pending", "approved", "deferred", "rejected")


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize_decisions(decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {name: 0 for name in ALLOWED_DECISIONS}
    unknown = 0
    approved_metadata_only = 0
    approved_value_change = 0
    approved_value_change_patch_ids = []

    for decision in decisions:
        human_decision = decision.get("human_decision")
        if human_decision in counts:
            counts[human_decision] += 1
        else:
            unknown += 1
        if human_decision == "approved":
            change_type = decision.get("change_type")
            if change_type == "metadata_only":
                approved_metadata_only += 1
            if change_type == "value_change" or decision.get("approved_action") == "revision_value_change":
                approved_value_change += 1
                approved_value_change_patch_ids.append(decision.get("patch_id"))

    warnings = []
    if approved_value_change > 0:
        warnings.append({
            "level": "red",
            "code": "approved_value_change_present",
            "message": "存在已通过的 value_change。不要在第一轮直接合并事实值。",
            "patch_ids": approved_value_change_patch_ids,
        })

    return {
        "total_decisions": len(decisions),
        "counts": counts,
        "unknown_decision_count": unknown,
        "approved_metadata_only_count": approved_metadata_only,
        "approved_value_change_count": approved_value_change,
        "approved_value_change_patch_ids": approved_value_change_patch_ids,
        "warnings": warnings,
    }


def summarize_quality_review_decisions(
    decisions_path: str = str(DEFAULT_DECISIONS),
    output_path: str = str(DEFAULT_OUTPUT),
) -> Dict[str, Any]:
    payload = load_json(Path(decisions_path))
    decisions = [item for item in payload.get("decisions", []) if isinstance(item, dict)]
    summary = summarize_decisions(decisions)
    registry = {name: SOURCE_REGISTRY.get(name) for name in ("zh_wikipedia", "wikidata", "nasa", "esa")}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decisions_path": decisions_path,
        "passed": True,
        "summary": summary,
        "formal_triples_written": False,
        "chroma_written": False,
        "neo4j_written": False,
        "active_source": ACTIVE_SOURCE,
        "source_registry": registry,
    }
    dump_json(Path(output_path), report)
    return report


def main() -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Summarize quality review human decisions without applying changes.")
    parser.add_argument("--decisions", default=str(DEFAULT_DECISIONS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = summarize_quality_review_decisions(args.decisions, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

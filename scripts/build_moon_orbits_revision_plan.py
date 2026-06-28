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
DEFAULT_PREFLIGHT = Path(BASE_DIR) / "evaluation" / "revision_value_change_preflight.json"
DEFAULT_OUTPUT = Path(BASE_DIR) / "evaluation" / "moon_orbits_revision_plan.json"
MOON_PATCH_ID = "source_conflict_v4_003"
URANUS_RADIUS_PATCH_ID = "source_conflict_v4_002"


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def by_patch(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {item.get("patch_id"): item for item in items if item.get("patch_id")}


def build_moon_orbits_revision_plan(
    *,
    decisions_path: str = str(DEFAULT_DECISIONS),
    preflight_path: str = str(DEFAULT_PREFLIGHT),
    output_path: str = str(DEFAULT_OUTPUT),
) -> Dict[str, Any]:
    decisions_payload = load_json(Path(decisions_path))
    preflight_payload = load_json(Path(preflight_path))
    decisions = by_patch(decisions_payload.get("decisions", []))
    preflight = by_patch(preflight_payload.get("items", []))
    moon_decision = decisions.get(MOON_PATCH_ID, {})
    moon_preflight = preflight.get(MOON_PATCH_ID, {})
    uranus_preflight = preflight.get(URANUS_RADIUS_PATCH_ID, {})
    formal_write_ready = (
        moon_decision.get("revision_status") == "validated"
        and moon_decision.get("human_decision") == "approved"
        and moon_decision.get("safe_to_apply") is True
        and moon_preflight.get("would_create_duplicate") is False
    )
    next_action = "approve_and_set_safe_to_apply_then_dry_run" if not formal_write_ready else "ready_for_explicit_apply_review"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "subject": moon_preflight.get("subject", "月球"),
        "relation": moon_preflight.get("relation", "ORBITS"),
        "patch_id": MOON_PATCH_ID,
        "original_value": (moon_preflight.get("original_values") or [""])[0],
        "proposed_value": moon_preflight.get("proposed_value") or moon_decision.get("user_proposed_value"),
        "duplicate_risk": bool(moon_preflight.get("would_create_duplicate")),
        "revision_status": moon_decision.get("revision_status", "none"),
        "human_decision": moon_decision.get("human_decision", "pending"),
        "safe_to_apply": bool(moon_decision.get("safe_to_apply")),
        "formal_write_ready": formal_write_ready,
        "next_required_user_action": next_action,
        "uranus_radius_guard": {
            "patch_id": URANUS_RADIUS_PATCH_ID,
            "blocked_by_duplicate_risk": bool(uranus_preflight.get("would_create_duplicate")),
            "recommended_next_action": uranus_preflight.get("recommended_next_action"),
            "revision_status": decisions.get(URANUS_RADIUS_PATCH_ID, {}).get("revision_status", "none"),
        },
        "formal_triples_written": False,
        "formal_data_written": False,
        "chroma_written": False,
        "neo4j_written": False,
        "active_source": ACTIVE_SOURCE,
        "source_registry": SOURCE_REGISTRY,
    }
    dump_json(Path(output_path), report)
    return report


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Build the Moon ORBITS revision dry-run plan report.")
    parser.add_argument("--decisions", default=str(DEFAULT_DECISIONS))
    parser.add_argument("--preflight", default=str(DEFAULT_PREFLIGHT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = build_moon_orbits_revision_plan(
        decisions_path=args.decisions,
        preflight_path=args.preflight,
        output_path=args.output,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

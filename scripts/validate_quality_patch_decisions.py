from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import BASE_DIR


DEFAULT_CANDIDATES = os.path.join(BASE_DIR, "data", "quality_patches", "source_conflict_resolution_candidates.json")
DEFAULT_DECISIONS = os.path.join(BASE_DIR, "data", "quality_patches", "source_conflict_resolution_decisions.template.json")
ALLOWED_HUMAN_DECISIONS = {"pending", "approved", "rejected", "deferred"}


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_decisions(decisions_path: str = DEFAULT_DECISIONS, candidates_path: str = DEFAULT_CANDIDATES) -> Dict[str, Any]:
    candidates_payload = load_json(candidates_path)
    decisions_payload = load_json(decisions_path)
    candidates = candidates_payload.get("candidates", [])
    decisions = decisions_payload.get("decisions", [])
    candidate_by_id = {item.get("patch_id"): item for item in candidates if item.get("patch_id")}
    decision_by_id = {item.get("patch_id"): item for item in decisions if item.get("patch_id")}
    errors: List[Dict[str, Any]] = []

    if len(candidate_by_id) != 8:
        errors.append({"check": "candidate_count", "expected": 8, "actual": len(candidate_by_id)})
    missing_decisions = sorted(set(candidate_by_id) - set(decision_by_id))
    extra_decisions = sorted(set(decision_by_id) - set(candidate_by_id))
    if missing_decisions:
        errors.append({"check": "missing_patch_id", "patch_ids": missing_decisions})
    if extra_decisions:
        errors.append({"check": "unknown_patch_id", "patch_ids": extra_decisions})

    for patch_id, decision in sorted(decision_by_id.items()):
        candidate = candidate_by_id.get(patch_id, {})
        human_decision = decision.get("human_decision")
        if human_decision not in ALLOWED_HUMAN_DECISIONS:
            errors.append({
                "check": "invalid_human_decision",
                "patch_id": patch_id,
                "actual": human_decision,
                "allowed": sorted(ALLOWED_HUMAN_DECISIONS),
            })
        if human_decision == "approved":
            if not str(decision.get("human_reason", "")).strip():
                errors.append({"check": "approved_requires_human_reason", "patch_id": patch_id})
            if decision.get("safe_to_apply") is not True:
                errors.append({"check": "approved_requires_safe_to_apply_true", "patch_id": patch_id})
            if decision.get("approved_action") != candidate.get("action"):
                errors.append({
                    "check": "approved_action_must_match_candidate_action",
                    "patch_id": patch_id,
                    "approved_action": decision.get("approved_action"),
                    "candidate_action": candidate.get("action"),
                })

    return {
        "passed": not errors,
        "decisions_path": decisions_path,
        "candidates_path": candidates_path,
        "candidate_count": len(candidate_by_id),
        "decision_count": len(decision_by_id),
        "errors": errors,
        "formal_data_written": False,
        "patches_applied": False,
    }


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Validate source conflict quality patch decisions without applying patches.")
    parser.add_argument("--decisions", default=DEFAULT_DECISIONS)
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES)
    args = parser.parse_args()
    report = validate_decisions(args.decisions, args.candidates)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

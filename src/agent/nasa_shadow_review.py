from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.preview_nasa_shadow_query_chain_adapter import build_adapter_preview, utc_now


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ID = "nasa"
DEFAULT_SHADOW_DIR = ROOT / "data" / "triples_shadow" / SOURCE_ID
DEFAULT_EVAL_REPORT = ROOT / "evaluation" / "four_source_expansion" / "nasa_shadow_json_retrieval_eval_phase48.json"


def _blocked_report(reason: str, shadow_dir: Path, eval_report_path: Path) -> Dict[str, Any]:
    return {
        "phase": "Phase 51",
        "mode": "nasa_shadow_review_only_query_bypass",
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "ready": False,
        "blocked_reason": reason,
        "shadow_dir": str(shadow_dir),
        "eval_report_path": str(eval_report_path),
        "adapter_mappings": [],
        "mapping_count": 0,
        "review_only_required": True,
        "active_source": ACTIVE_SOURCE,
        "default_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "data_write": False,
    }


def run_nasa_shadow_review_preview(
    *,
    shadow_dir: str | Path = DEFAULT_SHADOW_DIR,
    eval_report_path: str | Path = DEFAULT_EVAL_REPORT,
    review_only: bool = False,
) -> Dict[str, Any]:
    """Explicit review-only entry point for NASA shadow JSON query previews."""
    shadow_path = Path(shadow_dir)
    eval_path = Path(eval_report_path)
    if review_only is not True:
        return _blocked_report("review_only_required", shadow_path, eval_path)

    report = build_adapter_preview(shadow_dir=shadow_path, eval_report_path=eval_path)
    report.update(
        {
            "phase": "Phase 51",
            "mode": "nasa_shadow_review_only_query_bypass",
            "review_only_required": True,
            "review_only": True,
            "default_query_path_changed": False,
            "gui_default_behavior_changed": False,
        }
    )
    return report

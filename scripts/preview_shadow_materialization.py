from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE
from src.source_control import get_source_schema_version, is_known_source


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unique_existing_paths(paths: Iterable[Any], source_dir: Path) -> List[Path]:
    seen = set()
    selected: List[Path] = []
    source_root = source_dir.resolve()
    for item in paths:
        path = Path(str(item)).resolve()
        if path in seen or not path.exists() or source_root not in (path, *path.parents):
            continue
        if path.name.endswith(("_triples.json", "_narratives.json")):
            selected.append(path)
            seen.add(path)
    return selected


def count_records(path: Path) -> int:
    try:
        payload = read_json(path)
    except Exception:
        return 0
    return len(payload) if isinstance(payload, list) else 0


def summarize_files(paths: List[Path]) -> Dict[str, Any]:
    triple_files = [path for path in paths if path.name.endswith("_triples.json")]
    narrative_files = [path for path in paths if path.name.endswith("_narratives.json")]
    return {
        "triple_files": len(triple_files),
        "narrative_files": len(narrative_files),
        "triple_records": sum(count_records(path) for path in triple_files),
        "narrative_records": sum(count_records(path) for path in narrative_files),
        "files": [str(path) for path in paths],
    }


def build_preview_report(source: str, *, base_dir: Path = ROOT) -> Dict[str, Any]:
    source_name = str(source or "").strip().lower()
    if not is_known_source(source_name):
        raise ValueError(f"Unknown source: {source}")
    source_dir = base_dir / "data" / "triples" / source_name
    summary_path = source_dir / "summary.json"
    summary = read_json(summary_path) if summary_path.exists() else {}
    selected = unique_existing_paths(summary.get("files_written", []), source_dir)
    selected_set = {path.resolve() for path in selected}
    all_files = sorted(source_dir.glob("*_triples.json")) + sorted(source_dir.glob("*_narratives.json"))
    stale = [path.resolve() for path in all_files if path.resolve() not in selected_set]

    return {
        "source": source_name,
        "source_schema_version": get_source_schema_version(source_name),
        "active_source_before": ACTIVE_SOURCE,
        "active_source_after": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "mode": "shadow_materialization_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary_path": str(summary_path),
        "summary_exists": summary_path.exists(),
        "selected": summarize_files(selected),
        "ignored_stale": {
            **summarize_files(stale),
            "sample_files": [str(path) for path in stale[:20]],
        },
        "write_plan": {
            "neo4j": "source namespace only; requires live service and manifest-filtered loader before import",
            "chroma": "source namespace only; requires local embedding model and manifest-filtered loader before import",
            "deletes_data_files": False,
            "changes_active_source": False,
        },
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Preview shadow namespace materialization inputs.")
    parser.add_argument("--source", choices=["nasa", "esa", "wikidata"], required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = build_preview_report(args.source)
    output = args.output or ROOT / "evaluation" / "source_expansion" / args.source / f"{args.source}_shadow_materialization_preview.json"
    write_json(Path(output), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_quality.page_quality import score_page


DEFAULT_REPORT = ROOT / "evaluation" / "source_quality" / "page_quality_sample_report.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def candidates_from_payload(payload: Any, source: str) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            items = payload["items"]
        elif isinstance(payload.get("accepted"), list):
            items = payload["accepted"]
        else:
            items = [payload]
    else:
        items = []
    candidates = []
    for item in items:
        if isinstance(item, dict):
            candidate = dict(item)
            if source and source != "generic":
                candidate.setdefault("source_name", source)
            candidates.append(candidate)
    return candidates


def build_report(candidates: Sequence[Dict[str, Any]], source: str) -> Dict[str, Any]:
    items = []
    triage_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for index, candidate in enumerate(candidates, start=1):
        result = score_page(candidate)
        triage_counts[result["triage"]] += 1
        reason_counts.update(result.get("reasons", []))
        items.append({
            "index": index,
            "source": source,
            "url": candidate.get("url") or candidate.get("source_url") or "",
            "title": candidate.get("title") or candidate.get("source_title") or "",
            **result,
        })
    return {
        "source": source,
        "mode": "local_page_quality_scoring",
        "total": len(items),
        "triage_counts": dict(sorted(triage_counts.items())),
        "top_reasons": dict(reason_counts.most_common(10)),
        "items": items,
    }


def print_summary(report: Dict[str, Any]) -> None:
    print(f"source={report['source']} total={report['total']}")
    print("triage | count")
    print("--- | ---:")
    for triage, count in report["triage_counts"].items():
        print(f"{triage} | {count}")
    if report["top_reasons"]:
        print("top_reasons=" + json.dumps(report["top_reasons"], ensure_ascii=False))


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Score local candidate science pages without network or formal writes.")
    parser.add_argument("--input-json", required=True, help="Candidate JSON file, raw JSON, frontier JSON, or list of records.")
    parser.add_argument("--source", default="generic", choices=("nasa", "esa", "wikidata", "generic"))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT))
    args = parser.parse_args(argv)

    payload = read_json(Path(args.input_json))
    candidates = candidates_from_payload(payload, args.source)
    report = build_report(candidates, args.source)
    write_json(Path(args.report_json), report)
    print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

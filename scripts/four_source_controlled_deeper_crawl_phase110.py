import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE


PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase110"
DOC_PATH = ROOT / "docs" / "four_source_controlled_deeper_crawl_phase110.md"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_gate(path: Path) -> dict:
    return _load(path)["gate_config"]


def allowed_by_gate(source: str, url: str, gate: dict) -> bool:
    source_gate = gate["sources"][source]
    haystack = url.lower()
    host = urlparse(url).netloc.lower()
    if not any(allowed in haystack or allowed in host for allowed in source_gate["allowlist"]):
        return False
    return not any(denied.replace(" ", "-") in haystack or denied in haystack for denied in source_gate["denylist"])


def classify(source: str, title: str, text: str, gate: dict) -> str:
    haystack = f"{title} {text}".lower()
    denied = gate["sources"][source]["denylist"]
    if any(token in haystack for token in denied):
        return "rejected"
    if source == "wikidata":
        return "accepted" if all(token in haystack for token in ("claim", "source")) else "thin"
    words = re.findall(r"\w+", haystack)
    if len(words) < 12:
        return "thin"
    return "accepted"


def fetch_url(url: str, timeout: int = 12) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "TololoAgent Phase110 evaluation-only preview"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(300_000)
            return {
                "status": "succeeded" if response.status == 200 else "failed",
                "status_code": response.status,
                "text": raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        return {"status": "failed", "status_code": exc.code, "text": "", "failure_reason": str(exc)}
    except Exception as exc:
        return {"status": "failed", "status_code": 0, "text": "", "failure_reason": str(exc)}


def _candidate_url(item: dict) -> str:
    return str(item.get("url_or_entity") or item.get("source_url") or item.get("url") or "")


def select_candidates(phase104: dict, gate: dict) -> dict[str, list[dict]]:
    selected = {source: [] for source in gate["sources"]}
    all_items = phase104["filtered_review_queue"] + phase104["rejected_queue"]
    seen: set[tuple[str, str]] = set()
    for item in all_items:
        source = item["source"]
        if source not in selected:
            continue
        url = _candidate_url(item)
        key = (source, url)
        if key in seen:
            continue
        seen.add(key)
        if not allowed_by_gate(source, url, gate):
            selected[source].append({**item, "gate_rejected_before_fetch": True, "gate_reject_reason": "allowlist_or_denylist"})
        else:
            selected[source].append(item)
        selected[source] = selected[source][: gate["sources"][source]["max_batch"]]
    return selected


def _preview_text(item: dict, fetched: dict, live_fetch: bool) -> str:
    if fetched.get("text"):
        return fetched["text"][:1200]
    sample = item.get("sample")
    return json.dumps(sample, ensure_ascii=False)[:1200] if sample else f"{item.get('title_or_id')} {_candidate_url(item)}"


def build_preview(phase109_gate: Path, phase104_report: Path, fetcher=fetch_url, live_fetch: bool = True) -> dict:
    gate_report = _load(phase109_gate)
    gate = gate_report["gate_config"]
    phase104 = _load(phase104_report)
    selected = select_candidates(phase104, gate)
    records = []
    stop_reasons: dict[str, str] = {}
    for source, items in selected.items():
        for item in items:
            url = _candidate_url(item)
            if item.get("gate_rejected_before_fetch"):
                fetched = {"status": "not_fetched", "status_code": 0, "text": ""}
                quality = "rejected"
                reason = item["gate_reject_reason"]
            elif live_fetch and source != "wikidata":
                fetched = fetcher(url)
                quality = classify(source, item["title_or_id"], _preview_text(item, fetched, live_fetch), gate)
                reason = "" if quality != "rejected" else "stop_condition_quality_gate"
            else:
                fetched = {"status": "not_fetched", "status_code": 0, "text": ""}
                quality = classify(source, item["title_or_id"], _preview_text(item, fetched, live_fetch), gate)
                reason = "" if quality != "rejected" else "stop_condition_quality_gate"
            if quality == "rejected" and source not in stop_reasons:
                stop_reasons[source] = reason or "quality_gate_rejected"
            records.append(
                {
                    "source": source,
                    "title_or_id": item["title_or_id"],
                    "url_or_entity": url,
                    "method": "live_fetch" if live_fetch and fetched["status"] != "not_fetched" else "gate_probe_existing_record",
                    "fetch_status": fetched["status"],
                    "status_code": fetched["status_code"],
                    "quality_status": quality,
                    "reject_reason": reason,
                    "text_excerpt": re.sub(r"\s+", " ", _preview_text(item, fetched, live_fetch))[:400],
                    "quality_flags": gate["sources"][source]["quality_gates"],
                }
            )
    counts = Counter(row["quality_status"] for row in records)
    by_source = {
        source: dict(Counter(row["quality_status"] for row in records if row["source"] == source))
        for source in gate["sources"]
    }
    return {
        "phase": "Phase110",
        "mode": "controlled_deeper_crawl_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_gate": str(phase109_gate.relative_to(ROOT)),
        "limits": {source: cfg["max_batch"] for source, cfg in gate["sources"].items()},
        "total_limit": gate["total_max_batch"],
        "total_attempted": len(records),
        "counts": dict(counts),
        "source_breakdown": by_source,
        "stop_reasons_by_source": stop_reasons,
        "preview_records": records,
        "live_fetch_used": live_fetch,
        "next_recommendation": "Phase111 normalize review preview only if reviewer accepts Phase110 preview quality; no apply/preflight",
        "production_ready": False,
        "preflight_allowed": False,
        "apply_preflight_allowed": False,
        "apply_approved": False,
        "ingest_approved": False,
        "preflight_approved": False,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "clear_source_ingestion_outputs_called": False,
    }


def _markdown(report: dict) -> str:
    lines = [
        "# Phase110 Controlled Deeper Crawl Preview",
        "",
        f"- total_attempted: {report['total_attempted']}",
        f"- counts: {report['counts']}",
        f"- source_breakdown: {report['source_breakdown']}",
        f"- stop_reasons: {report['stop_reasons_by_source']}",
        f"- live_fetch_used: {report['live_fetch_used']}",
        "- production/preflight/apply/ingest: false",
        "",
        "## Records",
    ]
    lines += [f"- {r['source']} `{r['quality_status']}` {r['title_or_id']} {r['url_or_entity']}" for r in report["preview_records"]]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict) -> list[Path]:
    paths = [
        PHASE_DIR / "controlled_deeper_crawl_preview_phase110.json",
        PHASE_DIR / "controlled_deeper_crawl_preview_phase110.md",
        DOC_PATH,
    ]
    for path in paths:
        if not output_allowed(path, allow_docs=path == DOC_PATH):
            raise ValueError(f"blocked output path: {path}")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    (PHASE_DIR / "controlled_deeper_crawl_preview_phase110.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "controlled_deeper_crawl_preview_phase110.md").write_text(_markdown(report), encoding="utf-8")
    DOC_PATH.write_text(_markdown(report), encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase110 controlled deeper crawl preview.")
    parser.add_argument("--phase109-gate", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase109" / "controlled_deeper_crawl_gate_phase109.json")
    parser.add_argument("--phase104-report", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase104" / "verdict_report_phase104.json")
    parser.add_argument("--no-live-fetch", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_preview(args.phase109_gate, args.phase104_report, live_fetch=not args.no_live_fetch)
    if args.write:
        write_outputs(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

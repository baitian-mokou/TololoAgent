import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import zh_mediawiki_network_diagnostics_phase119 as phase119


ROOT = phase119.ROOT
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase125"
DOC_PATH = ROOT / "docs" / "zh_controlled_live_reentry_preview_phase125.md"


def probe_titles() -> list[str]:
    return ["太阳", "月球", "地球"]


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(PHASE_DIR.resolve()) or (
        allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())
    )


def _endpoint(title: str) -> str:
    encoded = quote(title)
    return (
        "https://zh.wikipedia.org/w/api.php?action=query&prop=extracts"
        f"&explaintext=1&titles={encoded}&format=json&utf8=1"
    )


def _encoding(content_type: str) -> str:
    return phase119._encoding(content_type)


def _extract_text(raw: bytes) -> str:
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        pages = payload.get("query", {}).get("pages", {})
        for page in pages.values():
            return page.get("extract", "") or ""
    except Exception:
        return ""
    return ""


def _fetch(url: str) -> tuple[int, str, bytes, int]:
    import time

    start = time.perf_counter()
    request = Request(url, headers={"User-Agent": "TololoAgent-Phase125-LiveReentry/1.0"})
    try:
        with urlopen(request, timeout=8) as response:
            raw = response.read()
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return response.status, response.headers.get("content-type", ""), raw, elapsed_ms
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return 0, "network_error", str(exc).encode("utf-8", errors="replace"), elapsed_ms


def _readable_chinese(text: str) -> bool:
    return "�" not in text and any("\u4e00" <= char <= "\u9fff" for char in text)


def _probe(title: str, fetcher) -> dict:
    endpoint = _endpoint(title)
    status_code, content_type, raw, elapsed_ms = fetcher(endpoint)
    ok = 200 <= status_code < 300
    text = _extract_text(raw) if ok else ""
    accepted = ok and _readable_chinese(text)
    return {
        "title": title,
        "endpoint": endpoint,
        "method": "mediawiki_plain_extract_title_probe",
        "status_code": status_code,
        "status": f"http_{status_code}" if status_code else "fetch_failed",
        "error": "" if ok else raw.decode("utf-8", errors="replace")[:200],
        "elapsed_ms": elapsed_ms,
        "content_type": content_type,
        "encoding": _encoding(content_type),
        "body_snippet_len": min(len(raw), 200) if ok else 0,
        "quality_verdict": "accepted_review_only" if accepted else ("rejected_no_readable_chinese" if ok else "failed"),
        "review_status": "pending_manual_review" if accepted else "not_in_review_queue",
        "queue_allowed": False,
        "production_ready": False,
    }


def _failure_layer(items: list[dict]) -> str:
    if all(item["status_code"] == 0 for item in items):
        return "network_or_timeout"
    if any(item["status_code"] >= 500 for item in items):
        return "http_5xx"
    if any(400 <= item["status_code"] < 500 for item in items):
        return "http_4xx_or_api_rejected"
    if any(item["quality_verdict"] == "rejected_no_readable_chinese" for item in items):
        return "parse_or_quality_gate"
    return "none"


def build_preview(fetcher=phase119.default_fetcher) -> dict:
    live_probe_used = fetcher is phase119.default_fetcher
    fetcher = _fetch if live_probe_used else fetcher
    items = [_probe(title, fetcher) for title in probe_titles()]
    succeeded = sum(1 for item in items if 200 <= item["status_code"] < 300)
    accepted = sum(1 for item in items if item["quality_verdict"] == "accepted_review_only")
    failed = sum(1 for item in items if item["quality_verdict"] == "failed")
    rejected = len(items) - accepted - failed
    return {
        "phase": "Phase125",
        "mode": "controlled_zh_live_reentry_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_report": "evaluation/four_source_expansion/phase124/zh_mediawiki_restored_network_recheck_phase124.json",
        "request_limit": 3,
        "live_probe_used": live_probe_used,
        "attempted": len(items),
        "succeeded": succeeded,
        "accepted": accepted,
        "rejected": rejected,
        "failed": failed,
        "failure_layer": _failure_layer(items),
        "items": items,
        "verdict": (
            "zh_live_reentry_preview_review_only_has_accepted"
            if accepted
            else "zh_live_reentry_preview_blocked"
        ),
        "recommended_next": "review Phase125 preview; no queue/apply/preflight approval",
        "queue_allowed": False,
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
        "active_source": "zh_wikipedia",
        "active_source_unchanged": True,
        "clear_source_ingestion_outputs_called": False,
    }


def markdown(report: dict) -> str:
    return "\n".join(
        [
            "# Phase125 Controlled ZH Live Re-entry Preview",
            "",
            f"- verdict: {report['verdict']}",
            f"- attempted/succeeded/accepted/rejected/failed: {report['attempted']}/{report['succeeded']}/{report['accepted']}/{report['rejected']}/{report['failed']}",
            f"- failure_layer: {report['failure_layer']}",
            f"- request_limit: {report['request_limit']}",
            "- queue/apply/preflight/ingest/production: false/false/false/false/false",
            "",
            "Accepted items are review-only pending manual review; no body text is persisted.",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    targets = [
        PHASE_DIR / "zh_controlled_live_reentry_preview_phase125.json",
        PHASE_DIR / "zh_controlled_live_reentry_preview_phase125.md",
        DOC_PATH,
    ]
    if not all(output_allowed(target, allow_docs=target == DOC_PATH) for target in targets):
        raise ValueError("output path not allowed")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    targets[0].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = markdown(report)
    targets[1].write_text(text, encoding="utf-8")
    targets[2].write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_preview()
    if args.write:
        write_outputs(report)
    print(json.dumps({"phase": report["phase"], "verdict": report["verdict"], "accepted": report["accepted"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

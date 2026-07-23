import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase119"
DOC_PATH = ROOT / "docs" / "zh_mediawiki_network_diagnostics_phase119.md"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def probe_plan() -> list[dict]:
    title = quote("太阳")
    return [
        {
            "method": "siteinfo_status_probe",
            "endpoint": "https://zh.wikipedia.org/w/api.php?action=query&meta=siteinfo&siprop=general&format=json&utf8=1",
        },
        {
            "method": "known_good_title_extract_probe",
            "endpoint": f"https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles={title}&format=json&utf8=1",
        },
    ]


def default_fetcher(url: str) -> tuple[int, str, bytes, int]:
    start = time.perf_counter()
    request = Request(url, headers={"User-Agent": "TololoAgent-Phase119-NetworkDiagnostics/1.0"})
    try:
        with urlopen(request, timeout=8) as response:
            raw = response.read(4096)
            elapsed = int((time.perf_counter() - start) * 1000)
            return response.status, response.headers.get("content-type", ""), raw, elapsed
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        return 0, "network_error", str(exc).encode("utf-8", errors="replace"), elapsed


def _encoding(content_type: str) -> str:
    lower = content_type.lower()
    if "charset=" in lower:
        return lower.split("charset=", 1)[1].split(";", 1)[0].strip()
    return "utf-8_assumed"


def _probe(row: dict, fetcher) -> dict:
    status, content_type, raw, elapsed_ms = fetcher(row["endpoint"])
    ok = 200 <= status < 300
    return {
        "endpoint": row["endpoint"],
        "method": row["method"],
        "status_code": status,
        "status": f"http_{status}" if status else "fetch_failed",
        "error": "" if ok else raw.decode("utf-8", errors="replace")[:200],
        "elapsed_ms": elapsed_ms,
        "content_type": content_type,
        "encoding": _encoding(content_type),
        "body_snippet_len": min(len(raw), 200) if ok else 0,
    }


def _failure_layer(probes: list[dict]) -> str:
    if all(probe["status_code"] == 0 for probe in probes):
        return "network_or_timeout"
    if any(probe["status_code"] and probe["status_code"] >= 500 for probe in probes):
        return "http_5xx"
    if any(probe["status_code"] and probe["status_code"] >= 400 for probe in probes):
        return "http_4xx_or_api_rejected"
    if probes[0]["status_code"] and not probes[1]["status_code"]:
        return "title_extract_network_or_timeout"
    if probes[0]["status_code"] and probes[1]["status_code"]:
        return "none_network_layer_reachable"
    return "unknown"


def build_diagnostics(fetcher=default_fetcher) -> dict:
    probes = [_probe(row, fetcher) for row in probe_plan()]
    siteinfo_ok = probes[0]["status_code"] == 200
    title_ok = probes[1]["status_code"] == 200
    network_reachable = any(probe["status_code"] for probe in probes)
    layer = _failure_layer(probes)
    return {
        "phase": "Phase119",
        "mode": "controlled_mediawiki_network_diagnostics",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_report": "evaluation/four_source_expansion/phase118/zh_offline_fixture_diagnostics_phase118.json",
        "request_limit": 2,
        "live_probe_used": fetcher is default_fetcher,
        "probes": probes,
        "network_reachable": network_reachable,
        "siteinfo_ok": siteinfo_ok,
        "known_good_title_ok": title_ok,
        "failure_layer": layer,
        "network_verdict": "mediawiki_network_reachable_no_queue_approval" if siteinfo_ok and title_ok else "mediawiki_network_still_blocked",
        "recommended_next": "review network layer result; do not queue zh until separately approved",
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


def _markdown(report: dict) -> str:
    return "\n".join(
        [
            "# Phase119 Controlled MediaWiki Network Diagnostics",
            "",
            f"- network_verdict: {report['network_verdict']}",
            f"- network_reachable: {report['network_reachable']}",
            f"- siteinfo_ok: {report['siteinfo_ok']}",
            f"- known_good_title_ok: {report['known_good_title_ok']}",
            f"- failure_layer: {report['failure_layer']}",
            f"- request_limit: {report['request_limit']}",
            f"- production/preflight/apply/ingest/queue: {report['production_ready']}/{report['preflight_allowed']}/{report['apply_approved']}/{report['ingest_approved']}/{report['queue_allowed']}",
            "",
            "Next: review diagnostics; no queue/apply/preflight/ingest approval.",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        PHASE_DIR / "zh_mediawiki_network_diagnostics_phase119.json",
        PHASE_DIR / "zh_mediawiki_network_diagnostics_phase119.md",
        DOC_PATH,
    ]
    for target in targets:
        if not output_allowed(target, allow_docs=target == DOC_PATH):
            raise ValueError(f"output path not allowed: {target}")
    targets[0].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = _markdown(report)
    targets[1].write_text(markdown, encoding="utf-8")
    targets[2].write_text(markdown, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_diagnostics()
    if args.write:
        write_outputs(report)
    print(json.dumps({"phase": report["phase"], "network_verdict": report["network_verdict"], "failure_layer": report["failure_layer"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

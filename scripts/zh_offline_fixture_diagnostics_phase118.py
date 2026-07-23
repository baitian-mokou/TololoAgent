import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase118"
DOC_PATH = ROOT / "docs" / "zh_offline_fixture_diagnostics_phase118.md"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def known_good_extract_fixture() -> dict:
    text = "太阳是太阳系中心的恒星，主要由氢和氦组成，通过核聚变释放光和热，并维持行星运行环境。"
    payload = json.dumps({"query": {"pages": {"1": {"title": "太阳", "extract": text}}}}, ensure_ascii=False).encode("utf-8")
    return {"title": "太阳", "content_type": "application/json; charset=utf-8", "payload": payload}


def decode_payload(raw: bytes, content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type or "", re.I)
    return raw.decode(match.group(1) if match else "utf-8", errors="replace")


def extract_plaintext(payload: str) -> str:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        stripped = re.sub(r"<[^>]+>", " ", payload or "")
        return re.sub(r"\s+", " ", html.unescape(stripped)).strip()
    pages = data.get("query", {}).get("pages", {})
    return " ".join(page.get("extract", "") for page in pages.values()).strip()


def classify_zh_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    lower = cleaned.lower()
    if not cleaned:
        return "failed"
    if "�" in cleaned or sum(token in lower for token in ("å", "æ", "ç", "é", "è", "ã")) >= 2:
        return "rejected"
    if any(token in lower for token in ("infobox", "table", "template", "caption", "模板", "信息框", "图注")):
        return "rejected"
    chinese = len(re.findall(r"[\u4e00-\u9fff]", cleaned))
    digits = sum(ch.isdigit() for ch in cleaned)
    if chinese < 18 or digits / max(len(cleaned), 1) > 0.25:
        return "rejected"
    return "accepted"


def diagnostic_urls(title: str = "太阳") -> dict:
    encoded = quote(title)
    return {
        "api_status_probe": "https://zh.wikipedia.org/w/api.php?action=query&meta=siteinfo&siprop=general&format=json&utf8=1",
        "known_good_title_probe": f"https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles={encoded}&format=json&utf8=1",
    }


def default_fetcher(url: str) -> tuple[int, str, bytes]:
    request = Request(url, headers={"User-Agent": "TololoAgent-Phase118-Diagnostics/1.0"})
    try:
        with urlopen(request, timeout=6) as response:
            return response.status, response.headers.get("content-type", ""), response.read(80_000)
    except Exception as exc:
        return 0, "network_error", str(exc).encode("utf-8", errors="replace")


def _network_probe(fetcher) -> dict:
    result = {}
    for name, url in diagnostic_urls().items():
        status, content_type, raw = fetcher(url)
        text = decode_payload(raw, content_type)
        result[name] = {
            "url": url,
            "status_code": status,
            "status": f"http_{status}" if status else "fetch_failed",
            "content_type": content_type,
            "encoding": re.search(r"charset=([^;\s]+)", content_type or "", re.I).group(1)
            if re.search(r"charset=([^;\s]+)", content_type or "", re.I)
            else "utf-8_assumed",
            "body_preview": text[:200] if status else "",
            "error": "" if status else text[:200],
        }
    return result


def build_diagnostics(fetcher=None) -> dict:
    fixture = known_good_extract_fixture()
    decoded = decode_payload(fixture["payload"], fixture["content_type"])
    narrative = extract_plaintext(decoded)
    encoding_logic_ok = "太阳系中心" in narrative or "太阳是太阳系" in narrative
    quality_gate_ok = classify_zh_text(narrative) == "accepted" and all(
        classify_zh_text(sample) == "rejected"
        for sample in ("å¤ªé˜³æ˜¯ä¸€é¢—æ�’æ˜Ÿ", "模板 infobox table caption 图注", "太阳 1234567890123456789012345")
    )
    network_status = _network_probe(fetcher) if fetcher else {"network_probe_used": False}
    network_ok = any(isinstance(row, dict) and row.get("status_code", 0) for row in network_status.values())
    likely = (
        "external_network_or_api_reachability_blocker"
        if encoding_logic_ok and quality_gate_ok and not network_ok
        else "network_reachable_review_phase117_fetch_errors_against_current_environment"
    )
    return {
        "phase": "Phase118",
        "mode": "zh_offline_fixture_network_diagnostics",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_report": "evaluation/four_source_expansion/phase117/zh_mediawiki_fetch_encoding_phase117.json",
        "offline_fixture": {
            "title": fixture["title"],
            "content_type": fixture["content_type"],
            "narrative": narrative,
            "quality_class": classify_zh_text(narrative),
        },
        "encoding_logic_ok": encoding_logic_ok,
        "quality_gate_ok": quality_gate_ok,
        "network_status": network_status,
        "likely_root_cause": likely,
        "quality_verdict": "offline_logic_ok_network_blocked" if likely.startswith("external") else "offline_logic_ok_network_diagnostic_available",
        "next_recommendation": "review network diagnostics; do not queue zh until live MediaWiki access succeeds",
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
            "# Phase118 zh Offline Fixture / Network Diagnostics",
            "",
            f"- quality_verdict: {report['quality_verdict']}",
            f"- encoding_logic_ok: {report['encoding_logic_ok']}",
            f"- quality_gate_ok: {report['quality_gate_ok']}",
            f"- likely_root_cause: {report['likely_root_cause']}",
            f"- network_status: {report['network_status']}",
            f"- production/preflight/apply/ingest: {report['production_ready']}/{report['preflight_allowed']}/{report['apply_approved']}/{report['ingest_approved']}",
            "",
            "Next: review diagnostics before any zh re-entry probe.",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        PHASE_DIR / "zh_offline_fixture_diagnostics_phase118.json",
        PHASE_DIR / "zh_offline_fixture_diagnostics_phase118.md",
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
    parser.add_argument("--network", action="store_true")
    args = parser.parse_args()
    report = build_diagnostics(default_fetcher if args.network else None)
    if args.write:
        write_outputs(report)
    print(json.dumps({"phase": report["phase"], "quality_verdict": report["quality_verdict"], "likely_root_cause": report["likely_root_cause"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

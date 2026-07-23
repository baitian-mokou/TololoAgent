import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase117"
DOC_PATH = ROOT / "docs" / "zh_mediawiki_fetch_encoding_phase117.md"
TITLES = ("太阳", "太阳系", "水星")


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def zh_seeds() -> list[dict]:
    seeds = []
    for title in TITLES:
        encoded = quote(title)
        seeds.append(
            {
                "title": title,
                "extract_url": f"https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles={encoded}&format=json&utf8=1",
                "parse_url": f"https://zh.wikipedia.org/w/api.php?action=parse&prop=text&page={encoded}&format=json&utf8=1",
            }
        )
    return seeds


def decode_payload(raw: bytes, content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type or "", re.I)
    encoding = match.group(1) if match else "utf-8"
    return raw.decode(encoding, errors="replace")


def default_fetcher(url: str) -> tuple[int, str, bytes]:
    request = Request(url, headers={"User-Agent": "TololoAgent-Phase117-Evaluation/1.0"})
    try:
        with urlopen(request, timeout=6) as response:
            return response.status, response.headers.get("content-type", ""), response.read(300_000)
    except Exception as exc:
        return 0, "network_error", str(exc).encode("utf-8", errors="replace")


def extract_plaintext(method: str, payload: str) -> str:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    if method == "extracts":
        pages = data.get("query", {}).get("pages", {})
        return " ".join(page.get("extract", "") for page in pages.values())
    html_text = data.get("parse", {}).get("text", {}).get("*", "")
    html_text = re.sub(r"<(script|style|table).*?</\1>", " ", html_text, flags=re.I | re.S)
    html_text = re.sub(r"<[^>]+>", " ", html_text)
    return re.sub(r"\s+", " ", html.unescape(html_text)).strip()


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


def _probe(seed: dict, fetcher) -> dict:
    attempts = []
    for method, url in (("extracts", seed["extract_url"]), ("parse", seed["parse_url"])):
        status, content_type, raw = fetcher(url)
        encoding = re.search(r"charset=([^;\s]+)", content_type or "", re.I)
        text = decode_payload(raw, content_type)
        narrative = extract_plaintext(method, text) if status else ""
        quality = classify_zh_text(narrative)
        attempts.append(
            {
                "endpoint": url,
                "method": f"mediawiki_{method}_utf8",
                "status_code": status,
                "status": f"http_{status}" if status else "fetch_failed",
                "content_type": content_type,
                "encoding": encoding.group(1) if encoding else "utf-8_assumed",
                "quality_class": quality,
                "failure_reason": "" if quality == "accepted" else "fetch_failed_or_quality_gate",
            }
        )
        if quality == "accepted":
            return {
                "source": "zh_wikipedia",
                "title": seed["title"],
                "endpoint": url,
                "method": f"mediawiki_{method}_utf8",
                "status_code": status,
                "encoding": attempts[-1]["encoding"],
                "quality_class": "accepted",
                "narrative": narrative[:800],
                "triples_preview": [
                    {"subject": seed["title"], "predicate": "SOURCE_URL", "object": url},
                    {"subject": seed["title"], "predicate": "HAS_ZH_REENTRY_PREVIEW_TEXT", "object": narrative[:220]},
                ],
                "attempts": attempts,
                "review_status": "candidate_only_pending_review",
            }
    return {
        "source": "zh_wikipedia",
        "title": seed["title"],
        "endpoint": seed["extract_url"],
        "method": "mediawiki_extracts_then_parse_utf8",
        "status_code": attempts[-1]["status_code"] if attempts else 0,
        "encoding": attempts[-1]["encoding"] if attempts else "unknown",
        "quality_class": "failed" if all(row["status_code"] == 0 for row in attempts) else "rejected",
        "narrative": "",
        "triples_preview": [],
        "attempts": attempts,
        "review_status": "blocked",
    }


def _count(records: list[dict]) -> dict:
    return {
        "attempted": len(records),
        "succeeded": sum(1 for row in records if row["status_code"] and row["status_code"] < 400),
        "accepted": sum(1 for row in records if row["quality_class"] == "accepted"),
        "rejected": sum(1 for row in records if row["quality_class"] == "rejected"),
        "failed": sum(1 for row in records if row["quality_class"] == "failed"),
    }


def build_preview(fetcher=default_fetcher) -> dict:
    records = [_probe(seed, fetcher) for seed in zh_seeds()]
    counts = _count(records)
    return {
        "phase": "Phase117",
        "mode": "zh_mediawiki_fetch_encoding_fix_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_reports": {
            "phase115": "evaluation/four_source_expansion/phase115/three_source_controlled_reentry_preview_phase115.json",
            "phase116": "evaluation/four_source_expansion/phase116/zh_nasa_strategy_fixes_phase116.json",
        },
        "live_probe_used": fetcher is default_fetcher,
        "records": records,
        "source_counts": counts,
        "zh_reentry_candidates": [row for row in records if row["quality_class"] == "accepted"],
        "quality_verdict": "zh_reentry_candidates_ready_for_review" if counts["accepted"] else "zh_mediawiki_fetch_encoding_still_blocked",
        "next_recommendation": "review accepted zh candidates only; do not apply or preflight",
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
            "# Phase117 zh MediaWiki Fetch/Encoding Fix Preview",
            "",
            f"- quality_verdict: {report['quality_verdict']}",
            f"- live_probe_used: {str(report['live_probe_used']).lower()}",
            f"- source_counts: {report['source_counts']}",
            f"- production/preflight/apply/ingest: {report['production_ready']}/{report['preflight_allowed']}/{report['apply_approved']}/{report['ingest_approved']}",
            "",
            "Next: review accepted zh candidates only; no apply/preflight.",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        PHASE_DIR / "zh_mediawiki_fetch_encoding_phase117.json",
        PHASE_DIR / "zh_mediawiki_fetch_encoding_phase117.md",
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
    report = build_preview()
    if args.write:
        write_outputs(report)
    print(json.dumps({"phase": report["phase"], "source_counts": report["source_counts"], "quality_verdict": report["quality_verdict"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

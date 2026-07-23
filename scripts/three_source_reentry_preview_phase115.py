import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase115"
DOC_PATH = ROOT / "docs" / "three_source_controlled_reentry_preview_phase115.md"
SOURCES = ("zh_wikipedia", "nasa", "esa")
PER_SOURCE_LIMIT = 3
TOTAL_LIMIT = 9


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def probe_seeds() -> dict[str, list[dict]]:
    zh_titles = ("太阳", "太阳系", "水星")
    return {
        "zh_wikipedia": [
            {
                "title": title,
                "url": f"https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles={quote(title)}&format=json",
                "method": "mediawiki_plaintext_extract_api",
            }
            for title in zh_titles
        ],
        "nasa": [
            {
                "title": "Juno images metadata",
                "url": "https://images-api.nasa.gov/search?q=Juno&media_type=image&page_size=3",
                "method": "images_api_structured_description",
            },
            {
                "title": "Juno WP REST",
                "url": "https://science.nasa.gov/wp-json/wp/v2/posts?per_page=3&search=Juno",
                "method": "science_wp_rest_body",
            },
            {
                "title": "Artemis WP REST",
                "url": "https://science.nasa.gov/wp-json/wp/v2/posts?per_page=1&search=Artemis",
                "method": "science_wp_rest_body",
            },
        ],
        "esa": [
            {"title": "Juice", "url": "https://www.esa.int/Science_Exploration/Space_Science/Juice", "method": "specific_article_body"},
            {
                "title": "Mars Express",
                "url": "https://www.esa.int/Science_Exploration/Space_Science/Mars_Express",
                "method": "specific_article_body",
            },
            {
                "title": "Solar Orbiter",
                "url": "https://www.esa.int/Science_Exploration/Space_Science/Solar_Orbiter",
                "method": "specific_article_body",
            },
        ],
    }


def allowed_url(source: str, url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    if source == "zh_wikipedia":
        return host == "zh.wikipedia.org" and path == "/w/api.php" and "explaintext=1" in query
    if source == "nasa":
        return (host == "images-api.nasa.gov" and path == "/search") or (host == "science.nasa.gov" and path.startswith("/wp-json/wp/v2/"))
    if source == "esa":
        if path.rstrip("/") == "/science_exploration/space_science":
            return False
        return host.endswith("esa.int") and not _bad_page_type(url)
    return False


def _bad_page_type(text: str) -> bool:
    lower = (text or "").lower()
    return any(token in lower for token in ("search", "gallery", "tag/", "category/", "listing"))


def classify_text(source: str, text: str) -> str:
    cleaned = re.sub(r"\s+", " ", html.unescape(text or "")).strip()
    lower = cleaned.lower()
    if not cleaned:
        return "failed"
    if any(token in lower for token in ("<html", "<!doctype", "latest news index", "listing", "footer")):
        return "rejected"
    if source == "zh_wikipedia":
        if any(token in lower for token in ("infobox", "table", "template", "模板", "信息框")):
            return "rejected"
        return "accepted" if len(re.findall(r"[\u4e00-\u9fff]", cleaned)) >= 40 else "conditional"
    if source == "nasa":
        if any(token in lower for token in ("photojournal navigation", "search latest content", "images-assets.nasa.gov")):
            return "rejected"
        return "accepted" if len(cleaned) >= 120 and not lower.startswith("juno is") else "conditional"
    if source == "esa":
        if any(token in lower for token in ("newsroom", "latest news", "space science home")):
            return "rejected"
        return "accepted" if len(cleaned) >= 80 else "conditional"
    return "rejected"


def default_fetcher(url: str) -> tuple[int, str, str]:
    request = Request(url, headers={"User-Agent": "TololoAgent-Phase115-Evaluation/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            content_type = response.headers.get("content-type", "")
            raw = response.read(300_000)
            return response.status, content_type, raw.decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, "network_error", str(exc)


def _strip_html(text: str) -> str:
    text = re.sub(r"<(script|style|nav|footer|header).*?</\1>", " ", text or "", flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _extract(source: str, method: str, payload: str) -> str:
    if not payload:
        return ""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return _strip_html(payload)
    if source == "zh_wikipedia":
        pages = data.get("query", {}).get("pages", {})
        return " ".join(page.get("extract", "") for page in pages.values())
    if source == "nasa" and method == "images_api_structured_description":
        items = data.get("collection", {}).get("items", [])
        return " ".join((item.get("data") or [{}])[0].get("description", "") for item in items[:3])
    if source == "nasa":
        parts = []
        for item in data[:3] if isinstance(data, list) else []:
            title = _strip_html(item.get("title", {}).get("rendered", ""))
            content = _strip_html(item.get("content", {}).get("rendered", ""))
            excerpt = _strip_html(item.get("excerpt", {}).get("rendered", ""))
            parts.append(" ".join(x for x in (title, content or excerpt) if x))
        return " ".join(parts)
    return _strip_html(payload)


def _record(source: str, seed: dict, fetcher) -> dict:
    if not allowed_url(source, seed["url"]):
        return {
            "source": source,
            "title": seed["title"],
            "url": seed["url"],
            "method": seed["method"],
            "status_code": 0,
            "status": "blocked_before_fetch",
            "content_type": "",
            "quality_class": "rejected",
            "reject_reason": "url_or_page_type_not_allowlisted",
            "narrative": "",
            "triples_preview": [],
        }
    status_code, content_type, payload = fetcher(seed["url"])
    narrative = _extract(source, seed["method"], payload)
    quality = classify_text(source, narrative if status_code else "")
    if seed["method"] == "images_api_structured_description" and quality == "accepted":
        quality = "conditional"
    return {
        "source": source,
        "title": seed["title"],
        "url": seed["url"],
        "method": seed["method"],
        "status_code": status_code,
        "status": f"http_{status_code}" if status_code else "fetch_failed",
        "content_type": content_type,
        "quality_class": quality,
        "reject_reason": "" if quality in {"accepted", "conditional"} else "failed_or_noise_gate",
        "narrative": narrative[:800],
        "triples_preview": (
            [
                {"subject": seed["title"], "predicate": "SOURCE_URL", "object": seed["url"]},
                {"subject": seed["title"], "predicate": "HAS_REENTRY_PREVIEW_TEXT", "object": narrative[:220]},
            ]
            if quality in {"accepted", "conditional"} and narrative
            else []
        ),
    }


def _count(rows: list[dict]) -> dict:
    return {
        "attempted": len(rows),
        "succeeded": sum(1 for row in rows if row["status_code"] and row["status_code"] < 400),
        "accepted": sum(1 for row in rows if row["quality_class"] == "accepted"),
        "conditional": sum(1 for row in rows if row["quality_class"] == "conditional"),
        "rejected": sum(1 for row in rows if row["quality_class"] == "rejected"),
        "failed": sum(1 for row in rows if row["quality_class"] == "failed"),
    }


def build_preview(fetcher=default_fetcher) -> dict:
    seeds = probe_seeds()
    total = sum(len(rows) for rows in seeds.values())
    if total > TOTAL_LIMIT or any(len(rows) > PER_SOURCE_LIMIT for rows in seeds.values()):
        raise ValueError("Phase115 probe limits exceeded")
    records = {source: [_record(source, seed, fetcher) for seed in seeds[source]] for source in SOURCES}
    counts = {source: _count(rows) for source, rows in records.items()}
    overall = "controlled_reentry_preview_partial_esa_ready_zh_nasa_need_review" if any(
        counts[source]["failed"] or counts[source]["rejected"] for source in ("zh_wikipedia", "nasa")
    ) else "controlled_reentry_preview_ready_for_review"
    return {
        "phase": "Phase115",
        "mode": "three_source_controlled_reentry_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_report": "evaluation/four_source_expansion/phase114/three_source_source_strategy_repair_phase114.json",
        "live_probe_used": fetcher is default_fetcher,
        "probe_limits": {"per_source_max": PER_SOURCE_LIMIT, "total_max": TOTAL_LIMIT, "total_attempted": total},
        "records_by_source": records,
        "source_counts": counts,
        "overall_verdict": overall,
        "next_recommendation": "review Phase115 records before any queue rebuild; no apply or preflight",
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
            "# Phase115 Controlled Re-entry Preview",
            "",
            f"- overall_verdict: {report['overall_verdict']}",
            f"- live_probe_used: {str(report['live_probe_used']).lower()}",
            f"- probe_limits: {report['probe_limits']}",
            f"- source_counts: {report['source_counts']}",
            f"- production/preflight/apply/ingest: {report['production_ready']}/{report['preflight_allowed']}/{report['apply_approved']}/{report['ingest_approved']}",
            "",
            "Next: review Phase115 records before any queue rebuild.",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        PHASE_DIR / "three_source_controlled_reentry_preview_phase115.json",
        PHASE_DIR / "three_source_controlled_reentry_preview_phase115.md",
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
    print(json.dumps({"phase": report["phase"], "source_counts": report["source_counts"], "overall_verdict": report["overall_verdict"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

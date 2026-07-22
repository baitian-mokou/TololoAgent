from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse


SCIENCE_TERMS = (
    "planet",
    "solar",
    "system",
    "moon",
    "asteroid",
    "comet",
    "orbit",
    "mass",
    "radius",
    "diameter",
    "atmosphere",
    "spacecraft",
    "mission",
    "science",
    "research",
    "astronomy",
    "planetary",
    "mars",
    "jupiter",
    "mercury",
    "venus",
    "earth",
    "saturn",
    "uranus",
    "neptune",
    "laboratory",
    "telescope",
    "spectroscopy",
    "dataset",
    "datasets",
    "exoplanet",
    "climate",
)
OFFICIAL_DOMAIN_TOKENS = (".gov", ".int", "nasa.gov", "esa.int")
ACADEMIC_DOMAIN_TOKENS = (".edu", ".ac.", "arxiv.org")
MEDIA_TOKENS = ("gallery", "image", "images", "video", "videos", "media", "multimedia")
BLOCKED_TOKENS = ("search", "tag", "tags", "privacy", "cookie", "cookies", "terms")
NEWS_TOKENS = ("news", "press", "release", "story", "stories", "blog", "update")
MISSION_TOKENS = ("mission", "spacecraft", "orbiter", "rover", "lander", "probe", "juice", "rosetta")
FACT_TOKENS = ("fact", "factsheet", "overview", "encyclopedia", "profile")
REFERENCE_TOKENS = ("reference", "references", "doi", "citation", "source:")
PUBLICATION_TOKENS = ("abstract", "paper", "preprint", "journal", "method", "results", "doi", "citation")
DEFAULT_ACCEPTED_MIN_SCORE = 70
DEFAULT_REVIEW_MIN_SCORE = 45


@dataclass
class PageQualityResult:
    score: int
    triage: str
    labels: List[str]
    reasons: List[str]
    metrics: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MiniHtmlStats(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: List[str] = []
        self.text_parts: List[str] = []
        self.link_count = 0
        self.table_count = 0
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "a":
            self.link_count += 1
        if tag == "table":
            self.table_count += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        elif not self._skip_depth:
            self.text_parts.append(text)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def count_hits(haystack: str, terms: Iterable[str]) -> int:
    lowered = haystack.lower()
    return sum(1 for term in terms if term in lowered)


def blocked_url_hits(url: str) -> int:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.lower().split("/") if part]
    query = parsed.query.lower()
    hits = 0
    if any(part in {"search", "tag", "tags", "privacy", "cookie", "cookies", "terms"} for part in path_parts):
        hits += 1
    if any(token in query for token in ("search=", "q=", "tag=", "privacy", "cookie")):
        hits += 1
    return hits


def add_label(labels: List[str], label: str) -> None:
    if label not in labels:
        labels.append(label)


def normalize_quality_context(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def taxonomy_hits(haystack: str, taxonomy: Any) -> int:
    if not isinstance(taxonomy, list):
        return 0
    lowered = haystack.lower().replace("-", " ").replace("_", " ")
    hits = 0
    for item in taxonomy:
        token = clean_text(item).lower().replace("-", " ").replace("_", " ")
        if token and (token in lowered or any(part in lowered for part in token.split())):
            hits += 1
    return hits


def html_stats(html: str) -> MiniHtmlStats:
    parser = MiniHtmlStats()
    parser.feed(html or "")
    return parser


def normalize_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    html = str(candidate.get("html") or "")
    stats = html_stats(html) if html else MiniHtmlStats()
    title = clean_text(candidate.get("title") or " ".join(stats.title_parts))
    text = clean_text(candidate.get("text") or candidate.get("raw_text") or " ".join(stats.text_parts))
    return {
        "url": clean_text(candidate.get("url") or candidate.get("source_url")),
        "title": title,
        "text": text,
        "html": html,
        "source_name": clean_text(candidate.get("source_name") or candidate.get("source")),
        "link_count": stats.link_count,
        "table_count": stats.table_count,
    }


def score_page(candidate: Dict[str, Any], quality_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    context = normalize_quality_context(quality_context)
    source_mode = clean_text(context.get("source_mode"))
    gate = context.get("quality_gate") if isinstance(context.get("quality_gate"), dict) else {}
    accepted_min_score = int(gate.get("accepted_min_score", DEFAULT_ACCEPTED_MIN_SCORE) or DEFAULT_ACCEPTED_MIN_SCORE)
    review_min_score = int(gate.get("review_min_score", DEFAULT_REVIEW_MIN_SCORE) or DEFAULT_REVIEW_MIN_SCORE)
    allow_exploratory = bool(gate.get("allow_exploratory", True))
    item = normalize_candidate(candidate)
    url = item["url"]
    title = item["title"]
    text = item["text"]
    haystack = f"{url} {title} {text}".lower()
    host = (urlparse(url).hostname or "").lower()
    url_signal = url.lower()
    title_url_signal = f"{url} {title}".lower()
    body_signal = text.lower()

    labels: List[str] = []
    reasons: List[str] = []
    score = 0

    blocked_hits = blocked_url_hits(url_signal)
    media_path_hits = count_hits(title_url_signal, MEDIA_TOKENS)
    media_body_hits = count_hits(body_signal, MEDIA_TOKENS)
    news_path_hits = count_hits(title_url_signal, NEWS_TOKENS)
    news_body_hits = count_hits(body_signal, NEWS_TOKENS)
    media_hits = media_path_hits + media_body_hits
    news_hits = news_path_hits + news_body_hits
    science_hits = count_hits(haystack, SCIENCE_TERMS)
    topic_hits = taxonomy_hits(haystack, context.get("topic_taxonomy"))
    fact_hits = count_hits(haystack, FACT_TOKENS)
    mission_hits = count_hits(haystack, MISSION_TOKENS)
    fact_path_hits = count_hits(title_url_signal, FACT_TOKENS)
    mission_path_hits = count_hits(title_url_signal, MISSION_TOKENS)
    reference_hits = count_hits(haystack, REFERENCE_TOKENS)
    publication_hits = count_hits(haystack, PUBLICATION_TOKENS)
    text_length = len(text)
    link_density = round(item["link_count"] / max(text_length / 1000, 1), 3)
    official_source = any(token in host for token in OFFICIAL_DOMAIN_TOKENS) or source_mode == "official_science"
    academic_source = any(token in host for token in ACADEMIC_DOMAIN_TOKENS) or source_mode == "academic"
    entity_data_source = source_mode == "entity_data"
    publisher_source = source_mode == "publisher"
    organization_source = host.endswith(".org") and not academic_source
    trusted_source = official_source or academic_source or entity_data_source
    if entity_data_source and not topic_hits and isinstance(context.get("topic_taxonomy"), list) and context.get("topic_taxonomy"):
        topic_hits = 1
    strong_science_page = trusted_source and bool(fact_path_hits or mission_path_hits or science_hits >= 5 or publication_hits >= 2)

    if entity_data_source:
        score += 20
        add_label(labels, "entity_data_source")
        reasons.append("entity data source mode")
    elif official_source:
        score += 20
        add_label(labels, "official_source")
        reasons.append("official or academic domain")
    elif academic_source:
        score += 18
        add_label(labels, "academic_source")
        reasons.append("academic or preprint domain")
    elif organization_source:
        score += 5
        add_label(labels, "organization_source")
        reasons.append("organization domain")
    elif publisher_source:
        score += 8
        add_label(labels, "publisher_source")
        reasons.append("publisher source mode")
    else:
        add_label(labels, "commercial_or_unknown_source")
    if topic_hits:
        score += min(10, topic_hits * 3)
        add_label(labels, "topic_taxonomy_context")
        reasons.append(f"topic taxonomy hits={topic_hits}")
    if science_hits:
        score += min(25, science_hits * 3)
        add_label(labels, "science_topic")
        reasons.append(f"science keyword hits={science_hits}")
    if fact_hits:
        score += 15
        add_label(labels, "fact_page")
        reasons.append("fact or overview page signal")
    if mission_hits:
        score += 15
        add_label(labels, "mission_page")
        reasons.append("mission page signal")
    if item["table_count"]:
        score += 25
        add_label(labels, "has_table")
        reasons.append("table evidence present")
    if reference_hits:
        score += min(10, reference_hits * 5)
        add_label(labels, "has_references")
        reasons.append("reference signal present")
    if publication_hits:
        score += min(15, publication_hits * 4)
        add_label(labels, "publication_page")
        reasons.append("publication/abstract signal")
    if text_length >= 300:
        score += 10
    elif text_length < 80:
        score -= 30
        add_label(labels, "short_text")
        reasons.append("very short text")
    else:
        score -= 10
        add_label(labels, "short_text")
        reasons.append("short text")
    if link_density > 20:
        score -= 20
        add_label(labels, "navigation_noise")
        reasons.append("high link density")
    if news_path_hits:
        score -= 15
        add_label(labels, "news_page")
        reasons.append("news/update signal")
    elif news_body_hits:
        score -= 5 if strong_science_page else 10
        add_label(labels, "navigation_noise" if strong_science_page else "news_page")
        reasons.append("news/update signal in body/navigation")
    if media_path_hits:
        score -= 35
        add_label(labels, "media_page")
        reasons.append("media/gallery signal")
    elif media_body_hits:
        score -= 5 if strong_science_page else 20
        add_label(labels, "navigation_noise" if strong_science_page else "media_page")
        reasons.append("media/gallery signal in body/navigation")
    if blocked_hits:
        score -= 45
        add_label(labels, "search_page" if "search" in url_signal else "policy_page")
        reasons.append("blocked path/content signal")
    if science_hits == 0:
        score -= 20
        add_label(labels, "low_signal")
        reasons.append("low science signal")

    if strong_science_page and score < 45:
        score = 45
        reasons.append("protected official science/fact/mission page floor")

    score = max(0, min(100, score))
    hard_reject = bool(media_path_hits or blocked_hits) or (link_density > 20 and not strong_science_page) or (text_length < 40 and science_hits == 0)
    if entity_data_source and text_length < 80 and score < review_min_score:
        score = review_min_score
        reasons.append("entity data metadata-only review floor")

    if hard_reject and not entity_data_source:
        triage = "rejected"
    elif news_path_hits and science_hits and allow_exploratory:
        triage = "exploratory"
    elif score >= accepted_min_score and ("fact_page" in labels or "mission_page" in labels or "has_table" in labels) and source_mode != "generic_unknown":
        triage = "accepted"
    elif score >= min(accepted_min_score, 60) and "official_source" in labels and "mission_page" in labels:
        triage = "accepted"
    elif (science_hits or topic_hits or entity_data_source) and score >= review_min_score:
        triage = "review_needed"
    elif science_hits or topic_hits or entity_data_source:
        triage = "review_needed"
    else:
        triage = "rejected"

    return PageQualityResult(
        score=score,
        triage=triage,
        labels=labels,
        reasons=reasons,
        metrics={
            "text_length": text_length,
            "link_density_estimate": link_density,
            "table_count": item["table_count"],
            "science_keyword_hits": science_hits,
            "topic_taxonomy_hits": topic_hits,
            "blocked_keyword_hits": blocked_hits + media_hits,
            "news_keyword_hits": news_hits,
            "path_media_keyword_hits": media_path_hits,
            "body_media_keyword_hits": media_body_hits,
            "path_news_keyword_hits": news_path_hits,
            "body_news_keyword_hits": news_body_hits,
            "reference_keyword_hits": reference_hits,
            "accepted_min_score": accepted_min_score,
            "review_min_score": review_min_score,
            "source_mode": source_mode,
        },
    ).as_dict()

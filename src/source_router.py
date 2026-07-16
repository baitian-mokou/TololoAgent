from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List


ENABLE_ENV = "TOLOLO_ENABLE_SOURCE_ROUTER"


@dataclass(frozen=True)
class RoutingTrace:
    enabled: bool
    query: str
    intent: str
    preferred_sources: List[str]
    reason: str
    replaces_default_answer: bool = False

    def as_dict(self) -> Dict[str, object]:
        return {
            "enabled": self.enabled,
            "query": self.query,
            "intent": self.intent,
            "preferred_sources": list(self.preferred_sources),
            "reason": self.reason,
            "replaces_default_answer": self.replaces_default_answer,
        }


class SourceRouterPreview:
    """Explainable routing preview only; never replaces default answers."""

    def __init__(self, enabled: bool | None = None):
        self.enabled = os.getenv(ENABLE_ENV) == "1" if enabled is None else bool(enabled)

    def route(self, query: str) -> Dict[str, object]:
        text = str(query or "")
        if not self.enabled:
            return RoutingTrace(
                enabled=False,
                query=text,
                intent="disabled",
                preferred_sources=[],
                reason=f"Set {ENABLE_ENV}=1 to enable source routing preview.",
            ).as_dict()

        intent = classify_query_intent(text)
        if intent == "structured_numerical_fact":
            preferred = ["nasa", "wikidata", "zh_wikipedia"]
            reason = "structured numerical fact: prefer nasa > wikidata > zh_wikipedia"
        elif intent == "identifier_or_ontology_fact":
            preferred = ["wikidata", "zh_wikipedia"]
            reason = "identifier/ontology fact: prefer wikidata > zh_wikipedia"
        else:
            preferred = ["zh_wikipedia"]
            reason = "narrative explanation: prefer zh_wikipedia"
        return RoutingTrace(
            enabled=True,
            query=text,
            intent=intent,
            preferred_sources=preferred,
            reason=reason,
        ).as_dict()


class SourceRouter:
    """Minimal keyword router for the GUI auto-source mode."""

    ALL_SOURCES = ["nasa", "wikidata", "zh_wikipedia", "esa"]

    ESA_KEYWORDS = (
        "juice",
        "rosetta",
        "gaia",
        "solar orbiter",
        "mars express",
        "esa",
        "探测任务",
        "航天任务",
        "探测器",
    )
    NUMERIC_KEYWORDS = (
        "质量",
        "半径",
        "直径",
        "大气",
        "成分",
        "物理参数",
        "距离",
        "平均半径",
        "质量是多少",
        "mass",
        "radius",
        "diameter",
        "distance",
        "atmosphere",
        "composition",
    )
    STRUCTURED_KEYWORDS = (
        "属于",
        "位于",
        "绕行",
        "发现者",
        "谁发现",
        "part of",
        "located in",
        "orbits",
    )
    NARRATIVE_KEYWORDS = (
        "为什么",
        "如何",
        "原理",
        "介绍",
        "解释",
        "形成",
        "历史",
        "发光",
        "生命",
    )

    def route(self, query: str) -> Dict[str, object]:
        text = str(query or "")
        lowered = text.lower()
        has_numeric = any(keyword in lowered for keyword in self.NUMERIC_KEYWORDS)
        has_structured = any(keyword in lowered for keyword in self.STRUCTURED_KEYWORDS)
        has_narrative = any(keyword in lowered for keyword in self.NARRATIVE_KEYWORDS)
        has_esa = any(keyword in lowered for keyword in self.ESA_KEYWORDS)

        if has_esa:
            return {
                "query": text,
                "intent": "esa_mission",
                "selected_sources": ["esa", "nasa", "wikidata", "zh_wikipedia"],
                "routing_reason": "esa mission keywords matched; keep esa first but search peer candidates in parallel",
                "fusion_mode": "peer_source_fusion",
            }
        if has_numeric and has_narrative:
            return {
                "query": text,
                "intent": "mixed_numeric_narrative",
                "selected_sources": list(self.ALL_SOURCES),
                "routing_reason": "query mixes numeric fact and explanation; use peer candidate sources and let relation-aware fusion decide authority",
                "fusion_mode": "peer_source_fusion",
            }
        if has_structured:
            return {
                "query": text,
                "intent": "structured_fact",
                "selected_sources": ["wikidata", "nasa", "zh_wikipedia", "esa"],
                "routing_reason": "structured relation keywords matched; keep wikidata first but search peer candidates in parallel",
                "fusion_mode": "peer_source_fusion",
            }
        if has_numeric:
            return {
                "query": text,
                "intent": "numeric_fact",
                "selected_sources": ["nasa", "wikidata", "zh_wikipedia", "esa"],
                "routing_reason": "numeric or physical-parameter keywords matched; keep nasa first but search peer candidates in parallel",
                "fusion_mode": "peer_source_fusion",
            }
        if has_narrative:
            return {
                "query": text,
                "intent": "narrative_explanation",
                "selected_sources": ["zh_wikipedia", "nasa", "esa", "wikidata"],
                "routing_reason": "narrative explanation keywords matched; keep zh_wikipedia first but search peer candidates in parallel",
                "fusion_mode": "peer_source_fusion",
            }
        return {
            "query": text,
            "intent": "uncertain",
            "selected_sources": list(self.ALL_SOURCES),
            "routing_reason": "router is uncertain; search peer candidate sources and let relation-aware fusion decide authority",
            "fusion_mode": "peer_source_fusion",
        }


def classify_query_intent(query: str) -> str:
    text = str(query or "").lower()
    numerical_terms = ("质量", "半径", "直径", "距离", "温度", "mass", "radius", "diameter", "distance", "temperature")
    ontology_terms = ("qid", "编号", "标识", "属于", "part_of", "located_in", "发现者", "discovered")
    if any(term in text for term in numerical_terms) or re.search(r"\d", text):
        return "structured_numerical_fact"
    if any(term in text for term in ontology_terms):
        return "identifier_or_ontology_fact"
    return "narrative_explanation"

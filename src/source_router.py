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


def classify_query_intent(query: str) -> str:
    text = str(query or "").lower()
    numerical_terms = ("质量", "半径", "直径", "距离", "温度", "mass", "radius", "diameter", "distance", "temperature")
    ontology_terms = ("qid", "编号", "标识", "属于", "part_of", "located_in", "发现者", "discovered")
    if any(term in text for term in numerical_terms) or re.search(r"\d", text):
        return "structured_numerical_fact"
    if any(term in text for term in ontology_terms):
        return "identifier_or_ontology_fact"
    return "narrative_explanation"

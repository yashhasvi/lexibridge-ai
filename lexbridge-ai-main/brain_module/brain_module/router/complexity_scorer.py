"""
ComplexityScorer — determines which fetcher(s) to activate for a query.

Scoring combines:
  - Query length (longer → more complex)
  - Multi-entity count (spaCy NER — but falls back to token heuristic)
  - Presence of comparative / causal language
  - Intent type from IntentClassifier

Output is a `FetcherPlan` listing which fetchers to run and their weight.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .intent_classifier import IntentClassifier, QueryIntent


# ---------------------------------------------------------------------------
# Fetcher identifiers
# ---------------------------------------------------------------------------

class FetcherName(str):
    FAST_RAG = "fast_rag"
    HYBRID = "hybrid"
    GRAPH_RAG = "graph_rag"
    LIGHTRAG = "lightrag"
    AGENTIC = "agentic"


@dataclass
class FetcherPlan:
    """Which fetchers to activate and their relative weight for RRF fusion."""
    fetchers: list[str]             # subset of FetcherName constants
    weights: dict[str, float]       # fetcher → weight (sum need not equal 1)
    complexity_score: float         # 0.0 (simple) – 1.0 (very complex)
    intent: QueryIntent = QueryIntent.UNKNOWN
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------------

_CAUSAL_RE = re.compile(
    r"\b(why|because|cause|reason|therefore|hence|due to|led to|result of|"
    r"explain|relationship|compare|contrast|differ|similar|both|all)\b",
    re.I,
)
_MULTI_ENTITY_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
)


def _count_tokens(text: str) -> int:
    return len(text.split())


def _count_named_entities(text: str) -> int:
    """Fast heuristic: count title-cased noun phrases without spaCy."""
    return len(_MULTI_ENTITY_RE.findall(text))


def _causal_language_present(text: str) -> bool:
    return bool(_CAUSAL_RE.search(text))


def _compute_complexity(query: str) -> float:
    """Return a complexity score in [0, 1]."""
    tokens = _count_tokens(query)
    entities = _count_named_entities(query)
    causal = _causal_language_present(query)

    # Normalise each signal to [0,1]
    length_score = min(tokens / 40.0, 1.0)         # ≥40 tokens → 1.0
    entity_score = min(entities / 5.0, 1.0)        # ≥5 entities → 1.0
    causal_score = 0.4 if causal else 0.0

    return min(0.4 * length_score + 0.35 * entity_score + 0.25 * causal_score, 1.0)


# ---------------------------------------------------------------------------
# ComplexityScorer
# ---------------------------------------------------------------------------

class ComplexityScorer:
    """
    Decide which fetchers to activate based on query intent + complexity.

    Routing table
    -------------
    intent=factual  + complexity<0.3  → fast_rag only
    intent=factual  + complexity≥0.3  → fast_rag + hybrid + graph_rag
    intent=technical                  → hybrid + fast_rag
    intent=multi_hop + complexity<0.5 → fast_rag + graph_rag + lightrag
    intent=multi_hop + complexity≥0.5 → all four fetchers
    intent=unanswerable               → fast_rag only (best-effort)
    fallback (unknown)                → fast_rag + hybrid + graph_rag + lightrag
    """

    def __init__(self, intent_classifier: IntentClassifier | None = None) -> None:
        self._classifier = intent_classifier or IntentClassifier()

    def plan(self, query: str) -> FetcherPlan:
        intent = self._classifier.classify(query)
        complexity = _compute_complexity(query)

        fetchers, weights, reasoning = self._route(intent, complexity)

        return FetcherPlan(
            fetchers=fetchers,
            weights=weights,
            complexity_score=round(complexity, 3),
            intent=intent,
            reasoning=reasoning,
        )

    @staticmethod
    def _route(
        intent: QueryIntent, complexity: float
    ) -> tuple[list[str], dict[str, float], str]:
        F = FetcherName

        if intent == QueryIntent.FACTUAL:
            if complexity < 0.3:
                return (
                    [F.FAST_RAG],
                    {F.FAST_RAG: 1.0},
                    "Simple factual → dense only",
                )
            return (
                [F.FAST_RAG, F.HYBRID, F.GRAPH_RAG],
                {F.FAST_RAG: 0.4, F.HYBRID: 0.3, F.GRAPH_RAG: 0.3},
                "Entity-rich factual → dense + hybrid + graph",
            )

        if intent == QueryIntent.TECHNICAL:
            return (
                [F.HYBRID, F.FAST_RAG],
                {F.HYBRID: 0.55, F.FAST_RAG: 0.45},
                "Technical → keyword-heavy hybrid first",
            )

        if intent == QueryIntent.MULTI_HOP:
            if complexity < 0.5:
                return (
                    [F.FAST_RAG, F.GRAPH_RAG, F.LIGHTRAG],
                    {F.FAST_RAG: 0.3, F.GRAPH_RAG: 0.35, F.LIGHTRAG: 0.35},
                    "Multi-hop moderate → dense + graph + LightRAG",
                )
            return (
                [F.FAST_RAG, F.HYBRID, F.GRAPH_RAG, F.LIGHTRAG],
                {F.FAST_RAG: 0.25, F.HYBRID: 0.2, F.GRAPH_RAG: 0.3, F.LIGHTRAG: 0.25},
                "Complex multi-hop → all fetchers",
            )

        if intent == QueryIntent.UNANSWERABLE:
            return (
                [F.FAST_RAG],
                {F.FAST_RAG: 1.0},
                "Opinion/unanswerable → best-effort dense",
            )

        if intent == QueryIntent.CHITCHAT:
            return (
                [],
                {},
                "Chitchat/greeting → no retrieval (instant template response)",
            )

        # Unknown fallback — cast a wide net
        return (
            [F.FAST_RAG, F.HYBRID, F.GRAPH_RAG, F.LIGHTRAG],
            {F.FAST_RAG: 0.3, F.HYBRID: 0.25, F.GRAPH_RAG: 0.25, F.LIGHTRAG: 0.2},
            "Unknown intent → all sources",
        )

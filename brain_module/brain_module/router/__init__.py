"""QueryRouter — public façade combining IntentClassifier + ComplexityScorer."""
from .intent_classifier import IntentClassifier, QueryIntent
from .complexity_scorer import ComplexityScorer, FetcherPlan, FetcherName

__all__ = [
    "IntentClassifier",
    "QueryIntent",
    "ComplexityScorer",
    "FetcherPlan",
    "FetcherName",
    "QueryRouter",
]


class QueryRouter:
    """Single entry-point: given a query string → return a FetcherPlan."""

    def __init__(self) -> None:
        self._classifier = IntentClassifier()
        self._scorer = ComplexityScorer(self._classifier)

    def route(self, query: str) -> FetcherPlan:
        return self._scorer.plan(query)

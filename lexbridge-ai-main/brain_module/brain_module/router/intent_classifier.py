"""
IntentClassifier — classifies a query into one of four intent types.

Uses a two-layer approach:
  1. Rule-based fast path (regex + keyword heuristics) — zero latency
  2. Embedding similarity fallback using intfloat/e5-small-v2

Intent types
------------
factual      → single-hop, lookup questions ("What is X?", "Who invented Y?")
multi_hop    → requires chaining multiple facts ("Why did X happen after Y?")
technical    → code/API/spec questions ("How do I configure X?", debug traces)
unanswerable → no factual answer expected ("What do you think about X?")
"""
from __future__ import annotations

import re
from enum import Enum
from functools import lru_cache
from typing import Optional

import numpy as np


class QueryIntent(str, Enum):
    FACTUAL = "factual"
    MULTI_HOP = "multi_hop"
    TECHNICAL = "technical"
    CHITCHAT = "chitchat"
    UNANSWERABLE = "unanswerable"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Rule-based patterns (fast path)
# ---------------------------------------------------------------------------

_FACTUAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(what is|what are|what was|what were|who is|who are|who was|when (was|is|did)|where (is|was|are|did))\b", re.I),
    re.compile(r"^(define|definition of|meaning of)\b", re.I),
    re.compile(r"^how (many|much|long|old|far|tall|big|large|heavy|fast|deep|wide|often)\b", re.I),
    re.compile(r"^(which|is there|are there|does|do|did|has|have|can|could|was|were)\b", re.I),
    re.compile(r"\b(capital of|population of|height of|distance from|founded in|located in|number of|capacity of)\b", re.I),
]

_MULTI_HOP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(why|how did|what caused|what led to|as a result of|because of|explain)\b", re.I),
    re.compile(r"\b(both|all|which of these|compare|difference between|similar to|relationship between)\b", re.I),
    re.compile(r"\b(first .* then|after .* (happened|occurred)|before .* (could|was))\b", re.I),
]

_TECHNICAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(code|function|class|method|api|library|package|module|import|error|exception|bug|debug|install|configure|setup|dockerfile|kubernetes|bash|shell|sql|python|javascript)\b", re.I),
    re.compile(r"(```|`[^`]+`|<[a-z]+>|--[a-z-]+|https?://|\.[a-z]{2,4}$)", re.I),
    re.compile(r"\b(how (do|to|can) (I|you|we)|step[- ]by[- ]step|tutorial|example of)\b", re.I),
]

_UNANSWERABLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(what do you (think|feel|believe)|in your opinion|should i|what would you)\b", re.I),
    re.compile(r"\b(best way to live|meaning of life|subjective|preference|recommend me)\b", re.I),
]

_CHITCHAT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*(hi|hello|hey|yo|hola|namaste|good (morning|afternoon|evening))\s*[!.?]*\s*$", re.I),
    re.compile(r"^\s*(how are you|how's it going|what's up|sup)\s*[?.!]*\s*$", re.I),
    re.compile(r"^\s*(thanks|thank you|thx|ok|okay|cool|great)\s*[!.?]*\s*$", re.I),
]


def _rule_classify(query: str) -> Optional[QueryIntent]:
    """Return intent from rules, or None to fall through to embedding."""
    q = query.strip()
    if any(p.search(q) for p in _CHITCHAT_PATTERNS):
        return QueryIntent.CHITCHAT
    if any(p.search(q) for p in _UNANSWERABLE_PATTERNS):
        return QueryIntent.UNANSWERABLE
    if any(p.search(q) for p in _TECHNICAL_PATTERNS):
        return QueryIntent.TECHNICAL
    if any(p.search(q) for p in _MULTI_HOP_PATTERNS):
        return QueryIntent.MULTI_HOP
    if any(p.search(q) for p in _FACTUAL_PATTERNS):
        return QueryIntent.FACTUAL
    return None


# ---------------------------------------------------------------------------
# Embedding-based fallback
# ---------------------------------------------------------------------------

_LABEL_EXEMPLARS: dict[QueryIntent, list[str]] = {
    QueryIntent.FACTUAL: [
        "What is the boiling point of water?",
        "Who invented the telephone?",
        "When was the Eiffel Tower built?",
        "How many people live in Tokyo?",
        "How tall is the Empire State Building?",
        "Where is the Sahara Desert located?",
        "How much does a Boeing 747 weigh?",
        "What is the capacity of Yankee Stadium?",
        "How long is the Great Wall of China?",
    ],
    QueryIntent.MULTI_HOP: [
        "Why did the Roman Empire fall?",
        "How did the discovery of penicillin change medicine?",
        "What are the differences between supervised and unsupervised learning?",
        "What happened after the Berlin Wall fell?",
        "How does climate change affect ocean currents?",
        "What is the relationship between inflation and unemployment?",
    ],
    QueryIntent.TECHNICAL: [
        "How do I configure a Redis connection pool in Python?",
        "What does the numpy broadcast error mean?",
        "How to write a Dockerfile for a FastAPI app?",
        "How do I set up SSH keys for GitHub?",
        "What is the time complexity of quicksort?",
        "How to fix a segmentation fault in C?",
    ],
    QueryIntent.UNANSWERABLE: [
        "What is the best programming language?",
        "Should I learn React or Vue?",
        "What do you think about AI ethics?",
        "Which country has the best food?",
        "What is the meaning of life?",
    ],
    QueryIntent.CHITCHAT: [
        "Hi",
        "Hello there",
        "How are you?",
        "Thanks!",
        "Good morning",
        "Hey what's up",
        "Okay cool",
    ],
}


@lru_cache(maxsize=1)
def _load_embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("intfloat/e5-small-v2")


@lru_cache(maxsize=1)
def _compute_label_embeddings():
    model = _load_embedder()
    label_vecs: dict[QueryIntent, np.ndarray] = {}
    for intent, examples in _LABEL_EXEMPLARS.items():
        # e5 models want a "query: " prefix for queries, "passage: " for passages
        vecs = model.encode([f"passage: {e}" for e in examples], normalize_embeddings=True)
        label_vecs[intent] = vecs.mean(axis=0)
    return label_vecs


_EMBEDDING_CONFIDENCE_THRESHOLD = 0.82


def _embedding_classify(query: str) -> QueryIntent:
    model = _load_embedder()
    label_vecs = _compute_label_embeddings()
    q_vec = model.encode([f"query: {query}"], normalize_embeddings=True)[0]
    best_intent = QueryIntent.UNKNOWN
    best_score = -1.0
    for intent, lvec in label_vecs.items():
        score = float(np.dot(q_vec, lvec))
        if score > best_score:
            best_score = score
            best_intent = intent
    if best_score < _EMBEDDING_CONFIDENCE_THRESHOLD:
        return QueryIntent.UNKNOWN
    return best_intent


# ---------------------------------------------------------------------------
# Public classifier
# ---------------------------------------------------------------------------

class IntentClassifier:
    """
    Classify user queries into intent categories.

    Rule-based fast-path runs first (no model load); falls back to
    embedding similarity if rules don't match.
    """

    def classify(self, query: str, use_embedding_fallback: bool = True) -> QueryIntent:
        result = _rule_classify(query)
        if result is not None:
            return result
        if use_embedding_fallback:
            return _embedding_classify(query)
        return QueryIntent.UNKNOWN

"""
BrainResponse and SourceCard — typed schema for every multi-source answer.

Every component in the pipeline works with these types as the canonical
output format.  JSON serialization is handled by ResponseFormatter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AnswerType(str, Enum):
    FACTUAL = "factual"
    MULTI_HOP = "multi_hop"
    OPINION = "opinion"
    UNANSWERABLE = "unanswerable"
    UNKNOWN = "unknown"


class RetrievalMethod(str, Enum):
    DENSE = "dense"
    GRAPH = "graph"
    BM25 = "bm25"
    HYBRID = "hybrid"
    LIGHTRAG_HYBRID = "lightrag_hybrid"
    LIGHTRAG_LOCAL = "lightrag_local"
    LIGHTRAG_GLOBAL = "lightrag_global"
    AGENTIC = "agentic"


@dataclass
class SourceCard:
    """One retrieved passage contributing to the final answer."""
    source_name: str            # "Stack Overflow", "Wikipedia", "HotpotQA" …
    excerpt: str                # The retrieved passage text
    url: str                    # Original attribution URL
    score: float                # Re-ranker score (0–1)
    retrieval_method: str       # One of RetrievalMethod values
    chunk_id: str = ""          # Internal chunk identifier
    citation_index: int = 0     # 1-based index used in [1][2][3] citations
    metadata: dict[str, Any] = field(default_factory=dict)

    def citation_block(self) -> str:
        """Return citation line as used inside the LLM prompt."""
        score_str = f"score {self.score:.2f}"
        return f"[{self.citation_index}] {self.source_name} ({score_str}): {self.excerpt}"


@dataclass
class RetrievalTrace:
    """Per-fetcher latency and result count telemetry."""
    fetcher: str
    latency_ms: float
    results_returned: int
    error: str | None = None


@dataclass
class BrainResponse:
    """
    Complete multi-source answer produced by the brain pipeline.

    `answer` contains inline [1][2][3] citations that map to
    `sources[i-1]` (1-based).
    """
    question: str
    answer: str                         # LLM-synthesized, with [N] citations
    sources: list[SourceCard]           # Ordered by re-ranker score desc
    confidence: float                   # Mean re-ranker score of used sources
    answer_type: AnswerType = AnswerType.UNKNOWN
    retrieval_trace: list[RetrievalTrace] = field(default_factory=list)
    latency_ms: float = 0.0
    model_used: str = ""
    reranker_used: str = ""
    error: str | None = None            # Set if pipeline partially failed
    guardrail_flags: list[str] = field(default_factory=list)  # e.g. ["negative_lead", "low_alignment"]

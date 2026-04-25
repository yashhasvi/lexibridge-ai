"""
Retrieval-level guardrails — filter reranked chunks before LLM synthesis.

Three complementary filters:
  1. filter_low_relevance   Drop chunks below an absolute score threshold
  2. filter_score_gap       Drop chunks far below the top-scored chunk (relative)
  3. cap_source_diversity    Prevent one source from dominating synthesis slots
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


def filter_low_relevance(
    chunks: list[dict[str, Any]],
    min_score: float = 0.15,
    min_keep: int = 1,
) -> list[dict[str, Any]]:
    """
    Drop chunks whose score falls below *min_score*.

    Always retains at least *min_keep* chunks (the highest-scored ones)
    so the LLM always has some context — even if it is weak.
    """
    if not chunks or min_score <= 0:
        return chunks

    above = [c for c in chunks if float(c.get("score", 0.0)) >= min_score]

    if len(above) >= min_keep:
        dropped = len(chunks) - len(above)
        if dropped:
            logger.info(
                "Retrieval filter: kept %d/%d chunks (min_score=%.3f)",
                len(above), len(chunks), min_score,
            )
        return above

    kept = sorted(chunks, key=lambda c: float(c.get("score", 0.0)), reverse=True)[:min_keep]
    logger.info(
        "Retrieval filter: all chunks below min_score=%.3f — keeping top %d by score",
        min_score, min_keep,
    )
    return kept


def filter_score_gap(
    chunks: list[dict[str, Any]],
    max_gap_ratio: float = 0.5,
    min_keep: int = 1,
) -> list[dict[str, Any]]:
    """
    Drop chunks whose score is less than *max_gap_ratio* of the top chunk's score.

    This works regardless of absolute score scale (raw RRF, cross-encoder, etc.).
    A chunk scoring 0.20 when the top chunk scores 0.80 has a ratio of 0.25
    and would be dropped with the default threshold of 0.5.
    """
    if len(chunks) <= min_keep or not chunks:
        return chunks

    top_score = max(float(c.get("score", 0.0)) for c in chunks)
    if top_score <= 0:
        return chunks

    threshold = top_score * max_gap_ratio
    kept = [c for c in chunks if float(c.get("score", 0.0)) >= threshold]

    if len(kept) < min_keep:
        kept = sorted(chunks, key=lambda c: float(c.get("score", 0.0)), reverse=True)[:min_keep]

    if len(kept) < len(chunks):
        logger.info(
            "Score-gap filter: kept %d/%d chunks (top=%.3f, threshold=%.3f)",
            len(kept), len(chunks), top_score, threshold,
        )

    return kept


def cap_source_diversity(
    chunks: list[dict[str, Any]],
    max_per_source: int = 2,
) -> list[dict[str, Any]]:
    """
    Prevent a single source from dominating all synthesis slots.

    Keeps at most *max_per_source* chunks from the same ``source`` value.
    Preserves the original ordering (assumed to be score-descending).
    """
    if max_per_source <= 0 or not chunks:
        return chunks

    counts: Counter[str] = Counter()
    result: list[dict[str, Any]] = []

    for chunk in chunks:
        source = chunk.get("source", "") or "unknown"
        if counts[source] < max_per_source:
            result.append(chunk)
            counts[source] += 1

    if len(result) < len(chunks):
        logger.info(
            "Source diversity cap: kept %d/%d chunks (max_per_source=%d)",
            len(result), len(chunks), max_per_source,
        )

    return result

"""
MultiSourceAggregator — orchestrates dedup → group → RRF fusion.

Takes the raw flat list from ParallelFetcher and returns a clean, fused,
and scored list ready for the CrossEncoderReranker.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from .deduplicator import exact_dedup, semantic_dedup
from .rrf_merger import rrf_merge
from .source_grouper import group_by_source

logger = logging.getLogger(__name__)


class MultiSourceAggregator:
    """
    Pipeline: exact_dedup → (optional semantic_dedup) → RRF fusion.

    Usage::

        aggregator = MultiSourceAggregator(semantic_dedup_threshold=0.92)
        fused_chunks = aggregator.aggregate(raw_chunks, fetcher_weights)
    """

    def __init__(
        self,
        semantic_dedup_threshold: float | None = None,
        top_n_before_rerank: int = 50,
    ) -> None:
        """
        Args:
            semantic_dedup_threshold: if set, run semantic dedup after exact
                dedup (requires sentence-transformers; adds latency ~100 ms).
            top_n_before_rerank: pass at most this many chunks to the reranker.
        """
        self._sem_threshold = semantic_dedup_threshold
        self._top_n = top_n_before_rerank

    def aggregate(
        self,
        chunks: list[dict[str, Any]],
        fetcher_weights: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Returns a single fused + sorted list of up to `top_n_before_rerank` chunks.
        """
        if not chunks:
            return []

        # 1. Exact dedup
        deduped = exact_dedup(chunks)
        logger.debug("Exact dedup: %d → %d chunks", len(chunks), len(deduped))

        # 2. Optional semantic dedup
        if self._sem_threshold is not None:
            deduped = semantic_dedup(deduped, threshold=self._sem_threshold)
            logger.debug("Semantic dedup: → %d chunks", len(deduped))

        # 3. Re-group by fetcher registration name for RRF
        #    _fetcher is set by ParallelFetcher to match the registry key
        #    (e.g. "lightrag"), which aligns with router weight keys.
        by_fetcher: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for chunk in deduped:
            fetcher = chunk.get("_fetcher") or chunk.get("retrieval_method", "unknown")
            by_fetcher[fetcher].append(chunk)

        # Sort each fetcher's list by original score descending (for RRF rank)
        for fetcher in by_fetcher:
            by_fetcher[fetcher].sort(key=lambda c: c.get("score", 0.0), reverse=True)

        # 4. RRF fusion
        fused = rrf_merge(dict(by_fetcher), weights=fetcher_weights)

        # 5. Trim to top-N
        return fused[: self._top_n]

"""
Hybrid fetcher — BM25 sparse retrieval + dense vector retrieval fused via RRF.

Reciprocal Rank Fusion (RRF) combines rankings from both retrievers
without needing score normalization.

BM25 is handled by the `rank_bm25` library over an in-memory index built
from the Parquet chunk archive.
"""
from __future__ import annotations

import logging
from typing import Any

from .base import AbstractFetcher, RetrievedChunk
from .fast_rag import FastRAGFetcher

logger = logging.getLogger(__name__)


def _rrf_score(rank: int, k: int = 60) -> float:
    """Reciprocal Rank Fusion score."""
    return 1.0 / (k + rank)


class HybridFetcher(AbstractFetcher):
    """
    BM25 + dense hybrid retrieval with Reciprocal Rank Fusion.

    The BM25 index is built lazily from a list of (chunk_id, text) tuples.
    For large datasets, use a pre-built index file (saved/loaded via `load_index()`).

    Best for:
      - Keyword-heavy technical queries (code errors, function names)
      - Queries mixing exact terms + semantic intent
    """

    def __init__(
        self,
        dense_fetcher: FastRAGFetcher,
        texts: list[tuple[str, str]] | None = None,  # (chunk_id, text) pairs
        rrf_k: int = 60,
        alpha: float = 0.5,  # unused in RRF but available for weighted fusion
    ) -> None:
        self.dense_fetcher = dense_fetcher
        self.rrf_k = rrf_k
        self.alpha = alpha
        self._bm25 = None
        self._chunk_ids: list[str] = []
        if texts:
            self._build_bm25(texts)

    def _build_bm25(self, texts: list[tuple[str, str]]) -> None:
        from rank_bm25 import BM25Okapi
        self._chunk_ids = [cid for cid, _ in texts]
        tokenized = [t.lower().split() for _, t in texts]
        self._bm25 = BM25Okapi(tokenized)
        logger.info("BM25 index built: %d documents.", len(tokenized))

    def load_texts_from_parquet(self, parquet_store: Any, source: str | None = None) -> None:
        """Build BM25 index from the Parquet chunk archive."""
        table = parquet_store.read_chunks(source=source)
        ids = table["chunk_id"].to_pylist()
        texts = table["text"].to_pylist()
        self._build_bm25(list(zip(ids, texts)))

    def fetch(
        self,
        query: str,
        top_k: int = 10,
        **kwargs: Any,
    ) -> list[RetrievedChunk]:
        # Dense retrieval
        dense_k = min(top_k * 3, 50)
        dense_results = self.dense_fetcher.fetch(query, top_k=dense_k, **kwargs)
        dense_ranks: dict[str, int] = {r.chunk_id: i for i, r in enumerate(dense_results)}

        # BM25 retrieval
        bm25_ranks: dict[str, int] = {}
        if self._bm25 is not None:
            tokens = query.lower().split()
            scores = self._bm25.get_scores(tokens)
            bm25_top = sorted(
                enumerate(scores), key=lambda x: x[1], reverse=True
            )[: dense_k]
            bm25_ranks = {self._chunk_ids[i]: rank for rank, (i, _) in enumerate(bm25_top)}

        # RRF fusion
        all_ids = set(dense_ranks) | set(bm25_ranks)
        fused: dict[str, float] = {}
        for cid in all_ids:
            score = 0.0
            if cid in dense_ranks:
                score += _rrf_score(dense_ranks[cid], self.rrf_k)
            if cid in bm25_ranks:
                score += _rrf_score(bm25_ranks[cid], self.rrf_k)
            fused[cid] = score

        top_ids = sorted(fused, key=lambda x: fused[x], reverse=True)[:top_k]

        # Build result list: dense results first, then fill from BM25-only hits
        id_to_result: dict[str, RetrievedChunk] = {r.chunk_id: r for r in dense_results}
        results: list[RetrievedChunk] = []
        for cid in top_ids:
            if cid in id_to_result:
                r = id_to_result[cid]
                r.score = fused[cid]
                results.append(r)
            # BM25-only hits would need an extra LanceDB lookup — omit for simplicity

        return results

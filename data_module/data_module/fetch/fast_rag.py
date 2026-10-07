"""
Fast RAG fetcher — dense vector similarity search via LanceDB.

Encodes the query with the same embedding model used during indexing,
then performs ANN search with optional scalar metadata filters.
"""
from __future__ import annotations

import logging
from typing import Any

from ..pipelines.embed import get_embedder
from ..storage.lance_store import LanceStore
from .base import AbstractFetcher, RetrievedChunk

logger = logging.getLogger(__name__)


class FastRAGFetcher(AbstractFetcher):
    """
    Pure dense retrieval — fastest path to relevant chunks.

    Best for:
      - Single-hop factual questions
      - Direct semantic similarity queries
      - High-throughput retrieval
    """

    def __init__(
        self,
        lance_store: LanceStore,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str = "cpu",
    ) -> None:
        self.store = lance_store
        self._embedder = get_embedder(embedding_model, device)

    def fetch(
        self,
        query: str,
        top_k: int = 10,
        source_filter: str | None = None,
        language_filter: str | None = None,
        min_score: int | None = None,
        **kwargs: Any,
    ) -> list[RetrievedChunk]:
        """
        Args:
            query: natural language query string.
            top_k: number of chunks to return.
            source_filter: e.g. "stackexchange" — filters by meta_source.
            language_filter: e.g. "en" — filters by meta_language.
            min_score: minimum quality score filter.
        """
        query_vector = self._embedder.encode([query])[0].tolist()

        # Build LanceDB filter string
        filter_parts: list[str] = []
        if source_filter:
            filter_parts.append(f"meta_source = '{source_filter}'")
        if language_filter:
            filter_parts.append(f"meta_language = '{language_filter}'")
        if min_score is not None:
            filter_parts.append(f"meta_score >= {min_score}")
        filters = " AND ".join(filter_parts) if filter_parts else None

        try:
            raw_results = self.store.search(query_vector, top_k=top_k, filters=filters)
        except Exception as exc:
            logger.error("FastRAGFetcher search failed: %s", exc)
            return []

        return [_row_to_chunk(r) for r in raw_results]


def _row_to_chunk(row: dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=row.get("chunk_id", ""),
        text=row.get("text", ""),
        score=float(row.get("_distance", 0.0)),
        source=row.get("meta_source", ""),
        source_url=row.get("meta_source_url", ""),
        license=row.get("meta_license", ""),
        tags=str(row.get("meta_tags", "")).split(","),
        chunk_type=row.get("chunk_type", ""),
        parent_question_id=row.get("parent_question_id", ""),
        metadata={k: v for k, v in row.items() if k.startswith("meta_")},
    )

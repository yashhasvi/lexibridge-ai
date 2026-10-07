"""
Transform deduplicator — removes duplicates from a stream of CanonicalQA records.

The validator handles exact content_hash dedup during ingestion.
This module provides optional semantic dedup using embedding cosine similarity
for near-duplicates (paraphrases, minor edits).
"""
from __future__ import annotations

import logging
from typing import Generator

import numpy as np

from ...schema.canonical import CanonicalQA

logger = logging.getLogger(__name__)


class SemanticDeduplicator:
    """
    Removes near-duplicate records using embedding cosine similarity.

    Maintains a rolling buffer of embeddings and skips any record whose
    maximum cosine similarity to the buffer exceeds `threshold`.

    NOTE: This is O(N²) in the worst case. For large datasets, use
    approximate nearest-neighbour (e.g. LanceDB self-query) instead.
    Use this only for smaller post-processing passes (< 500k records).
    """

    def __init__(
        self,
        embedder: object,  # must have .encode(texts: list[str]) -> np.ndarray
        threshold: float = 0.97,
        buffer_size: int = 50_000,
    ) -> None:
        self.embedder = embedder
        self.threshold = threshold
        self.buffer_size = buffer_size
        self._embeddings: list[np.ndarray] = []

    def deduplicate(
        self, records: Generator[CanonicalQA, None, None]
    ) -> Generator[CanonicalQA, None, None]:
        total = skipped = 0
        for record in records:
            total += 1
            text = record.title + " " + record.body[:200]
            emb = self.embedder.encode([text])[0]
            emb = emb / (np.linalg.norm(emb) + 1e-9)

            if self._embeddings:
                matrix = np.array(self._embeddings[-self.buffer_size :])
                sims = matrix @ emb
                if sims.max() > self.threshold:
                    skipped += 1
                    continue

            self._embeddings.append(emb)
            yield record

        logger.info("Semantic dedup: %d total, %d skipped (%.1f%%)", total, skipped, skipped / max(total, 1) * 100)

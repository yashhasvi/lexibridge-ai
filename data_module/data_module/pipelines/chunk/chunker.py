"""
Chunker — applies a chunking strategy to a stream of CanonicalQA records
and yields ChunkRecord objects ready for embedding.
"""
from __future__ import annotations

import logging
from typing import Generator

from ...schema.canonical import CanonicalQA
from ...schema.chunk import ChunkRecord
from .strategies import Strategy, STRATEGY_MAP

logger = logging.getLogger(__name__)


class Chunker:
    """
    Converts CanonicalQA records into ChunkRecords using a named strategy.

    The chunking_policy name is stored in each ChunkRecord's metadata so that
    re-indexing with a different strategy is safe (old chunks can be filtered out).
    """

    def __init__(
        self,
        strategy: Strategy | str = Strategy.CANONICAL_QA,
        max_tokens: int = 512,
    ) -> None:
        if isinstance(strategy, str):
            strategy = Strategy(strategy)
        self.strategy = strategy
        self.max_tokens = max_tokens
        self._fn = STRATEGY_MAP[strategy]

    def chunk(self, record: CanonicalQA) -> list[ChunkRecord]:
        chunks = self._fn(record, self.max_tokens)
        # Stamp chunking_policy into metadata
        for c in chunks:
            c.metadata.chunking_policy = self.strategy.value
        return chunks

    def chunk_stream(
        self, records: Generator[CanonicalQA, None, None]
    ) -> Generator[ChunkRecord, None, None]:
        total_records = total_chunks = 0
        for record in records:
            total_records += 1
            chunks = self.chunk(record)
            total_chunks += len(chunks)
            yield from chunks
        logger.info(
            "Chunked %d records → %d chunks (strategy=%s)",
            total_records,
            total_chunks,
            self.strategy.value,
        )

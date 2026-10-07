"""
Batch embedder — processes ChunkRecords in batches and adds embeddings.

Handles retry on transient failures (network/GPU OOM) with exponential backoff.
Updates ChunkRecord.metadata with embedding_model and embedding_dim.
"""
from __future__ import annotations

import logging
import time
from typing import Generator

from ...schema.chunk import ChunkRecord
from .embedder import get_embedder

logger = logging.getLogger(__name__)


class BatchEmbedder:
    """
    Consumes a stream of ChunkRecords, embeds in batches, and yields
    ChunkRecords with the `embedding` field populated.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        batch_size: int = 256,
        device: str = "cpu",
        max_retries: int = 3,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.device = device
        self.max_retries = max_retries
        self._embedder = None

    def _get_embedder(self):
        if self._embedder is None:
            self._embedder = get_embedder(self.model_name, self.device)
        return self._embedder

    def embed_batch(self, chunks: list[ChunkRecord]) -> list[ChunkRecord]:
        """Embed a batch of chunks and return them with embeddings set."""
        embedder = self._get_embedder()
        texts = [c.text for c in chunks]

        for attempt in range(self.max_retries):
            try:
                embeddings = embedder.encode(texts)
                dim = embedder.dim
                result = []
                for chunk, emb in zip(chunks, embeddings):
                    updated = chunk.model_copy(
                        update={
                            "embedding": emb.tolist(),
                        }
                    )
                    updated.metadata.embedding_model = self.model_name
                    updated.metadata.embedding_dim = dim
                    result.append(updated)
                return result
            except Exception as exc:
                wait = 2 ** attempt
                logger.warning(
                    "Embedding attempt %d/%d failed: %s. Retrying in %ds…",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    wait,
                )
                time.sleep(wait)

        # All retries exhausted — return chunks without embeddings
        logger.error("All embedding retries exhausted for batch of %d chunks.", len(chunks))
        return chunks

    def embed_stream(
        self, chunks: Generator[ChunkRecord, None, None]
    ) -> Generator[ChunkRecord, None, None]:
        """Stream-process chunks in batches."""
        batch: list[ChunkRecord] = []
        total = 0
        for chunk in chunks:
            batch.append(chunk)
            if len(batch) >= self.batch_size:
                yield from self.embed_batch(batch)
                total += len(batch)
                batch = []
                if total % 10_000 == 0:
                    logger.info("Embedded %d chunks…", total)
        # Flush remaining
        if batch:
            yield from self.embed_batch(batch)
            total += len(batch)
        logger.info("Embedding complete: %d chunks total.", total)

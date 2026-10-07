"""
Embedder — generates dense vector embeddings for ChunkRecords.

Supports:
  - sentence-transformers (default, local, free)
  - OpenAI text-embedding-3-* (requires OPENAI_API_KEY)

The embedding model name and dimension are stored in ChunkRecord.metadata
so that the index can be safely rebuilt when the model changes.
"""
from __future__ import annotations

import logging
from typing import Generator

import numpy as np

from ...schema.chunk import ChunkRecord

logger = logging.getLogger(__name__)


class SentenceTransformersEmbedder:
    """Local embedder using sentence-transformers library."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s on %s", self.model_name, self.device)
            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    @property
    def dim(self) -> int:
        return self._get_model().get_sentence_embedding_dimension()

    def encode(self, texts: list[str]) -> np.ndarray:
        model = self._get_model()
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)


class OpenAIEmbedder:
    """Remote embedder using OpenAI API (requires OPENAI_API_KEY env var)."""

    def __init__(self, model_name: str = "text-embedding-3-small") -> None:
        self.model_name = model_name
        self._dim_map = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}

    @property
    def dim(self) -> int:
        return self._dim_map.get(self.model_name, 1536)

    def encode(self, texts: list[str]) -> np.ndarray:
        import openai
        response = openai.embeddings.create(model=self.model_name, input=texts)
        return np.array([item.embedding for item in response.data], dtype=np.float32)


def get_embedder(model_name: str, device: str = "cpu"):
    """Factory: returns the correct embedder based on model name prefix."""
    if model_name.startswith("text-embedding"):
        return OpenAIEmbedder(model_name)
    return SentenceTransformersEmbedder(model_name, device)

"""
EmbeddingCache — LRU cache for query embedding vectors.

Wraps any embedder (sentence-transformers or OpenAI) to avoid re-encoding
the same query text on every request. Cache key is normalised query text.

For a RAG system seeing repeated queries, this saves ~50-100ms per request
since embedding model inference is skipped on cache hits.

Environment variables
---------------------
EMBEDDING_CACHE_ENABLED  : "true" to enable (default: true)
EMBEDDING_CACHE_MAXSIZE  : max entries in LRU cache (default: 2048)
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """
    LRU cache wrapping an embedder's ``encode`` method.

    Usage::

        from data_module.pipelines.embed import get_embedder
        raw_embedder = get_embedder("sentence-transformers/all-MiniLM-L6-v2")
        cached = EmbeddingCache(raw_embedder, maxsize=2048)
        vec = cached.encode(["What is Python?"])  # first call: computes
        vec = cached.encode(["What is Python?"])  # second call: cache hit
    """

    def __init__(self, embedder: Any, *, maxsize: int = 2048, enabled: bool = True) -> None:
        self._embedder = embedder
        self._maxsize = maxsize
        self._enabled = enabled
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._hits = 0
        self._misses = 0

    @property
    def model_name(self) -> str:
        return getattr(self._embedder, "model_name", "unknown")

    @property
    def dim(self) -> int:
        return self._embedder.dim

    @property
    def stats(self) -> dict[str, int]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._cache),
            "maxsize": self._maxsize,
        }

    def encode(self, texts: list[str]) -> np.ndarray:
        """
        Encode texts, using cached vectors when available.

        Cache operates on individual strings. Mixed hits/misses within a
        batch are handled correctly — only uncached texts hit the model.
        """
        if not self._enabled or not texts:
            return self._embedder.encode(texts)

        results: list[np.ndarray | None] = [None] * len(texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            key = self._normalise(text)
            cached_vec = self._cache.get(key)
            if cached_vec is not None:
                self._cache.move_to_end(key)
                results[i] = cached_vec
                self._hits += 1
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)
                self._misses += 1

        if uncached_texts:
            new_vecs = self._embedder.encode(uncached_texts)
            for j, idx in enumerate(uncached_indices):
                vec = new_vecs[j]
                results[idx] = vec
                key = self._normalise(uncached_texts[j])
                self._put(key, vec)

        return np.array(results, dtype=np.float32)

    def _put(self, key: str, vec: np.ndarray) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)
        self._cache[key] = vec

    @staticmethod
    def _normalise(text: str) -> str:
        return " ".join(text.strip().lower().split())

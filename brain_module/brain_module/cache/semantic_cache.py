"""
SemanticCache — embedding-similarity cache for near-duplicate queries.

Unlike the exact-match ``QueryCache`` (SHA256 of normalised text), this cache
embeds incoming queries and checks cosine similarity against all stored query
embeddings.  A paraphrased query like "capital of France" vs "what city is the
capital of France?" will hit the cache even though the text differs.

Design:
  - Stores (query_embedding, response_json) pairs in an in-process list.
  - On ``get()``, encodes the query and does a brute-force cosine scan.
  - Returns the best match if similarity >= threshold (default 0.92).
  - Bounded by ``maxsize``; evicts oldest entries on overflow.
  - Thread-safe for the single-writer / multi-reader async pattern.

The cache is intentionally in-process (no Redis) because:
  1. Embedding vectors are small (384 floats = ~1.5 KB each).
  2. Brute-force scan over ≤1024 vectors takes <1ms.
  3. Avoids serialising numpy arrays to Redis.

Environment variables
---------------------
SEMANTIC_CACHE_ENABLED    : "true" to enable (default: true)
SEMANTIC_CACHE_THRESHOLD  : cosine similarity threshold (default: 0.92)
SEMANTIC_CACHE_MAXSIZE    : max cached entries (default: 1024)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class SemanticCache:
    """
    Embedding-similarity cache for near-duplicate query matching.

    Usage::

        cache = SemanticCache(embedder=embedder)
        hit = await cache.get("What is the capital of France?")
        if hit is None:
            result = run_pipeline(...)
            await cache.set("What is the capital of France?", result)
    """

    def __init__(
        self,
        embedder: Any,
        *,
        threshold: float = 0.92,
        maxsize: int = 1024,
        enabled: bool = True,
    ) -> None:
        self._embedder = embedder
        self._threshold = threshold
        self._maxsize = maxsize
        self._enabled = enabled

        self._keys: list[str] = []
        self._embeddings: list[np.ndarray] = []
        self._values: list[str] = []  # JSON-serialised response dicts
        self._timestamps: list[float] = []

        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._keys),
            "maxsize": self._maxsize,
            "threshold": self._threshold,
        }

    async def get(self, query: str) -> dict[str, Any] | None:
        if not self._enabled or not self._embeddings or not query.strip():
            self._misses += 1
            return None

        try:
            query_vec = self._embed(query)
            stored = np.array(self._embeddings)

            query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-9)
            stored_norms = stored / (
                np.linalg.norm(stored, axis=1, keepdims=True) + 1e-9
            )
            similarities = stored_norms @ query_norm

            best_idx = int(np.argmax(similarities))
            best_sim = float(similarities[best_idx])

            if best_sim >= self._threshold:
                self._hits += 1
                logger.debug(
                    "SemanticCache HIT: sim=%.4f query=%r matched=%r",
                    best_sim, query[:60], self._keys[best_idx][:60],
                )
                try:
                    return json.loads(self._values[best_idx])
                except json.JSONDecodeError:
                    return None

        except Exception as exc:
            logger.warning("SemanticCache get() error: %s", exc)

        self._misses += 1
        return None

    async def set(
        self, query: str, response_dict: dict[str, Any]
    ) -> None:
        if not self._enabled or not query.strip():
            return

        try:
            query_vec = self._embed(query)
            serialised = json.dumps(response_dict, ensure_ascii=False)

            if len(self._keys) >= self._maxsize:
                self._keys.pop(0)
                self._embeddings.pop(0)
                self._values.pop(0)
                self._timestamps.pop(0)

            self._keys.append(query.strip())
            self._embeddings.append(query_vec)
            self._values.append(serialised)
            self._timestamps.append(time.time())

        except Exception as exc:
            logger.warning("SemanticCache set() error: %s", exc)

    def _embed(self, text: str) -> np.ndarray:
        vecs = self._embedder.encode([text])
        return vecs[0]

    async def clear(self) -> None:
        self._keys.clear()
        self._embeddings.clear()
        self._values.clear()
        self._timestamps.clear()

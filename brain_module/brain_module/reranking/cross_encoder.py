"""
CrossEncoderReranker — re-scores candidate chunks against the query using
a cross-encoder model, then returns the top-K.

Default model: cross-encoder/ms-marco-MiniLM-L-6-v2
  • Fast (6-layer MiniLM)
  • Trained on MS MARCO passage retrieval
  • Scores in (-∞, +∞); we normalise to [0, 1] via sigmoid

Alternative: BAAI/bge-reranker-v2-m3 (multilingual, higher quality, ~4× slower)
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=4)
def _load_cross_encoder(model_name: str):
    from sentence_transformers.cross_encoder import CrossEncoder
    return CrossEncoder(model_name)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


class CrossEncoderReranker:
    """
    Re-ranks a list of chunk dicts against a query string.

    Usage::

        reranker = CrossEncoderReranker()
        top_chunks = reranker.rerank(query, candidates, top_k=10)
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model = None  # lazy-loaded on first call

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_model(self):
        if self._model is None:
            logger.info("Loading cross-encoder: %s", self._model_name)
            self._model = _load_cross_encoder(self._model_name)
        return self._model

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Args:
            query:      the user's question.
            candidates: list of normalised chunk dicts (from aggregator).
            top_k:      number of top-scoring chunks to return.

        Returns:
            Up to `top_k` chunk dicts with `score` replaced by the
            cross-encoder sigmoid score (0-1).
        """
        if not candidates:
            return []

        model = self._get_model()

        pairs = [(query, c.get("text", "")) for c in candidates]

        try:
            raw_scores = model.predict(pairs)
        except Exception as exc:
            logger.error("CrossEncoder.predict failed: %s", exc)
            # Fall back to RRF score
            for c in candidates:
                c["score"] = float(c.get("rrf_score", c.get("score", 0.0)))
            return sorted(candidates, key=lambda c: c["score"], reverse=True)[:top_k]

        scored = []
        for chunk, raw_score in zip(candidates, raw_scores):
            normalised = _sigmoid(float(raw_score))
            c = dict(chunk)
            c["score"] = normalised
            scored.append(c)

        scored.sort(key=lambda c: c["score"], reverse=True)
        return scored[:top_k]

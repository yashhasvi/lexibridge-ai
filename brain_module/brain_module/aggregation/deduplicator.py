"""
Deduplicator — removes near-duplicate chunks from the aggregated pool.

Two-stage dedup:
  1. Exact hash dedup (SHA256 of normalised text)
  2. Semantic dedup via cosine similarity on sentence embeddings
     (only if exact dedup doesn't reduce pool enough)
"""
from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@lru_cache(maxsize=2)
def _load_embedder(model_name: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalise_text(text: str) -> str:
    """Lower + strip whitespace for hash comparison."""
    return " ".join(text.lower().split())


def exact_dedup(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove chunks with identical normalised text. Keeps first occurrence."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for chunk in chunks:
        h = _text_hash(_normalise_text(chunk.get("text", "")))
        if h not in seen:
            seen.add(h)
            unique.append(chunk)
    return unique


def semantic_dedup(
    chunks: list[dict[str, Any]],
    *,
    threshold: float = 0.92,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> list[dict[str, Any]]:
    """
    Remove chunks whose cosine similarity to an already-kept chunk exceeds
    `threshold`.  Requires sentence-transformers.
    """
    if len(chunks) <= 1:
        return chunks

    try:
        model = _load_embedder(embedding_model)
    except Exception as exc:
        logger.warning("semantic_dedup: could not load model, skipping. %s", exc)
        return chunks

    texts = [c.get("text", "") for c in chunks]
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    kept_indices: list[int] = []
    for i, vec_i in enumerate(vecs):
        is_dup = False
        for j in kept_indices:
            sim = float(np.dot(vec_i, vecs[j]))
            if sim >= threshold:
                is_dup = True
                break
        if not is_dup:
            kept_indices.append(i)

    return [chunks[i] for i in kept_indices]

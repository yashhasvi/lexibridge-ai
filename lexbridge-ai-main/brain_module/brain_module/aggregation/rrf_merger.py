"""
RRF Merger — Reciprocal Rank Fusion across multiple retrieval lists.

RRF formula: score(d) = Σ_r  1 / (k + rank_r(d))
where k=60 is the standard smoothing constant.

Each fetcher's list is treated as a ranked list; the fused score replaces
the individual fetcher scores for downstream re-ranking.
"""
from __future__ import annotations

from typing import Any


_RRF_K = 60


def rrf_merge(
    ranked_lists: dict[str, list[dict[str, Any]]],
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """
    Merge multiple ranked chunk lists using Reciprocal Rank Fusion.

    Args:
        ranked_lists: {fetcher_name: [chunk_dict, ...]} — already ranked
                      (highest score first) per fetcher.
        weights:      optional per-fetcher multiplier (default 1.0 for all).

    Returns:
        A single flat list of chunk dicts, sorted by descending RRF score.
        Each chunk has `rrf_score` added to its metadata.
    """
    weights = weights or {}

    # chunk_id → (chunk_dict, rrf_score accumulator)
    merged: dict[str, tuple[dict[str, Any], float]] = {}

    for fetcher, chunks in ranked_lists.items():
        w = weights.get(fetcher, 1.0)
        for rank, chunk in enumerate(chunks, start=1):
            cid = chunk.get("chunk_id") or _fallback_id(chunk)
            contrib = w / (_RRF_K + rank)

            if cid in merged:
                existing_chunk, existing_score = merged[cid]
                merged[cid] = (existing_chunk, existing_score + contrib)
            else:
                merged[cid] = (dict(chunk), contrib)

    result: list[dict[str, Any]] = []
    for chunk, rrf_score in merged.values():
        chunk["rrf_score"] = rrf_score
        result.append(chunk)

    result.sort(key=lambda c: c["rrf_score"], reverse=True)
    return result


def _fallback_id(chunk: dict[str, Any]) -> str:
    """Generate a stable id from text when chunk_id is absent."""
    import hashlib
    text = chunk.get("text", "")[:200]
    return hashlib.md5(text.encode()).hexdigest()

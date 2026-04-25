"""
SentenceCompressor — extractive sentence-level context compression.

After reranking selects top-K chunks, this module:
  1. Splits each chunk into sentences.
  2. Computes cosine similarity between each sentence and the query.
  3. Keeps only sentences scoring above a threshold (or the top-N per chunk).
  4. Reassembles compressed chunks with dramatically fewer tokens.

This is a "HUGE WIN" per the production optimisation guide — fewer tokens
fed to the LLM means faster generation, lower cost, and less noise.

No LLM call required — purely extractive via sentence-transformers.

Environment variables
---------------------
CONTEXT_COMPRESSION_ENABLED     : "true" to enable (default: true)
CONTEXT_COMPRESSION_MIN_SCORE   : min cosine sim to keep a sentence (default: 0.25)
CONTEXT_COMPRESSION_TOP_SENTS   : max sentences to keep per chunk (default: 5)
"""
from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_SENT_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z\"\'])|(?<=\n)\s*(?=\S)"
)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using regex heuristics."""
    raw = _SENT_SPLIT_RE.split(text.strip())
    sentences = [s.strip() for s in raw if s.strip() and len(s.strip()) > 10]
    return sentences if sentences else [text.strip()]


class SentenceCompressor:
    """
    Extractive sentence compression for retrieval chunks.

    Usage::

        compressor = SentenceCompressor()
        compressed = compressor.compress(query, chunks)
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        min_similarity: float = 0.25,
        top_sentences_per_chunk: int = 5,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str = "cpu",
    ) -> None:
        self._enabled = enabled
        self._min_sim = min_similarity
        self._top_n = top_sentences_per_chunk
        self._model_name = model_name
        self._device = device
        self._embedder = None

    def _get_embedder(self):
        if self._embedder is None:
            from data_module.pipelines.embed import get_embedder
            self._embedder = get_embedder(self._model_name, self._device)
        return self._embedder

    def compress(
        self,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Compress chunks by keeping only query-relevant sentences.

        Args:
            query: the user query.
            chunks: list of normalised chunk dicts (must have "text" key).

        Returns:
            New list of chunk dicts with compressed "text" fields.
            Original chunk order and metadata are preserved.
        """
        if not self._enabled or not chunks or not query.strip():
            return chunks

        try:
            return self._compress_impl(query, chunks)
        except Exception as exc:
            logger.warning("Context compression failed, returning original chunks: %s", exc)
            return chunks

    def _compress_impl(
        self, query: str, chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        all_sentences: list[str] = []
        chunk_sentence_ranges: list[tuple[int, int]] = []

        for chunk in chunks:
            text = chunk.get("text", "")
            sentences = _split_sentences(text)
            start = len(all_sentences)
            all_sentences.extend(sentences)
            chunk_sentence_ranges.append((start, len(all_sentences)))

        if not all_sentences:
            return chunks

        embedder = self._get_embedder()
        query_vec = embedder.encode([query])[0]
        sent_vecs = embedder.encode(all_sentences)

        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-9)
        sent_norms = sent_vecs / (np.linalg.norm(sent_vecs, axis=1, keepdims=True) + 1e-9)
        similarities = sent_norms @ query_norm

        compressed_chunks: list[dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            start, end = chunk_sentence_ranges[i]
            if start == end:
                compressed_chunks.append(chunk)
                continue

            chunk_sims = similarities[start:end]
            chunk_sents = all_sentences[start:end]

            scored = sorted(
                zip(chunk_sents, chunk_sims, range(len(chunk_sents))),
                key=lambda x: x[1],
                reverse=True,
            )

            kept = []
            for sent, sim, orig_idx in scored:
                if len(kept) >= self._top_n:
                    break
                if sim >= self._min_sim or not kept:
                    kept.append((orig_idx, sent))

            kept.sort(key=lambda x: x[0])
            compressed_text = " ".join(sent for _, sent in kept)

            new_chunk = dict(chunk)
            new_chunk["text"] = compressed_text
            new_chunk["_original_length"] = len(chunk.get("text", ""))
            new_chunk["_compressed_length"] = len(compressed_text)
            compressed_chunks.append(new_chunk)

        total_orig = sum(c.get("_original_length", 0) for c in compressed_chunks)
        total_comp = sum(c.get("_compressed_length", 0) for c in compressed_chunks)
        if total_orig > 0:
            ratio = (1 - total_comp / total_orig) * 100
            logger.debug(
                "Context compression: %d -> %d chars (%.0f%% reduction across %d chunks)",
                total_orig, total_comp, ratio, len(chunks),
            )

        return compressed_chunks

"""
ParallelFetcher — runs multiple fetchers concurrently via asyncio.gather.

Each fetcher's results are tagged with the fetcher name and returned as a
flat list of dicts with uniform keys so the aggregation layer can work with
them regardless of which backend produced them.

Compatible with both:
  - sync fetchers (data_module AbstractFetcher subclasses)
  - async fetchers (LightRAGFetcher)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from ..response.schema import RetrievalTrace
from .fetcher_registry import FetcherRegistry

logger = logging.getLogger(__name__)

# Keys expected in every normalised chunk dict
CHUNK_KEYS = ("chunk_id", "text", "score", "source", "source_url", "retrieval_method", "metadata")


def _normalise_chunk(raw: Any, fetcher_name: str) -> dict[str, Any]:
    """
    Convert a data_module RetrievedChunk *or* a raw dict to a normalised dict.
    """
    if isinstance(raw, dict):
        chunk = dict(raw)
    else:
        # data_module RetrievedChunk dataclass
        chunk = {
            "chunk_id": getattr(raw, "chunk_id", ""),
            "text": getattr(raw, "text", ""),
            "score": float(getattr(raw, "score", 0.0)),
            "source": getattr(raw, "source", ""),
            "source_url": getattr(raw, "source_url", ""),
            "retrieval_method": fetcher_name,
            "metadata": getattr(raw, "metadata", {}),
        }

    # Ensure all expected keys exist
    for key in CHUNK_KEYS:
        chunk.setdefault(key, "" if key != "metadata" else {})

    if not chunk["retrieval_method"]:
        chunk["retrieval_method"] = fetcher_name

    chunk["_fetcher"] = fetcher_name
    return chunk


async def _run_fetcher(
    name: str,
    fetcher: Any,
    query: str,
    top_k: int,
    timeout_s: float | None = None,
) -> tuple[str, list[dict[str, Any]], float, str | None]:
    """
    Run one fetcher (sync or async) and return (name, chunks, latency_ms, error).
    """
    t0 = time.perf_counter()
    error: str | None = None
    chunks: list[dict[str, Any]] = []

    async def _invoke_fetcher() -> Any:
        if asyncio.iscoroutinefunction(getattr(fetcher, "afetch", None)):
            return await fetcher.afetch(query, top_k=top_k)
        if asyncio.iscoroutinefunction(getattr(fetcher, "fetch", None)):
            return await fetcher.fetch(query, top_k=top_k)
        # Sync fetcher — run in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fetcher.fetch(query, top_k=top_k))

    try:
        if timeout_s and timeout_s > 0:
            raw = await asyncio.wait_for(_invoke_fetcher(), timeout=timeout_s)
        else:
            raw = await _invoke_fetcher()

        chunks = [_normalise_chunk(r, name) for r in (raw or [])]
    except asyncio.TimeoutError:
        error = f"timeout after {timeout_s:.1f}s" if timeout_s else "timeout"
        logger.warning("Fetcher %s timed out: %s", name, error)
    except Exception as exc:
        error = str(exc)
        logger.error("Fetcher %s failed: %s", name, exc)

    latency_ms = (time.perf_counter() - t0) * 1000
    return name, chunks, latency_ms, error


class ParallelFetcher:
    """
    Run a subset of registered fetchers in parallel and return merged results.

    Usage::

        results, traces = await parallel_fetcher.run(
            query="What is LightRAG?",
            fetcher_names=["fast_rag", "lightrag"],
            top_k=20,
        )
    """

    def __init__(self, registry: FetcherRegistry) -> None:
        self._registry = registry
        timeout_env = os.getenv("FETCHER_TIMEOUT_SECONDS", "12")
        try:
            self._fetcher_timeout_s = float(timeout_env)
        except ValueError:
            self._fetcher_timeout_s = 12.0

    async def run(
        self,
        query: str,
        fetcher_names: list[str],
        top_k: int = 20,
    ) -> tuple[list[dict[str, Any]], list[RetrievalTrace]]:
        """
        Returns (all_chunks, retrieval_traces) where:
          - all_chunks is a flat list of normalised chunk dicts
          - retrieval_traces carries per-fetcher latency telemetry
        """
        active: list[tuple[str, Any]] = []
        for name in fetcher_names:
            fetcher = self._registry.get(name)
            if fetcher is None:
                logger.warning("Fetcher %r not registered — skipping", name)
                continue
            active.append((name, fetcher))

        if not active:
            logger.warning("No active fetchers for query: %s", query[:60])
            return [], []

        coros = [
            _run_fetcher(name, fetcher, query, top_k, timeout_s=self._fetcher_timeout_s)
            for name, fetcher in active
        ]
        results = await asyncio.gather(*coros, return_exceptions=False)

        all_chunks: list[dict[str, Any]] = []
        traces: list[RetrievalTrace] = []
        for name, chunks, latency_ms, error in results:
            all_chunks.extend(chunks)
            traces.append(
                RetrievalTrace(
                    fetcher=name,
                    latency_ms=round(latency_ms, 1),
                    results_returned=len(chunks),
                    error=error,
                )
            )
            logger.debug(
                "Fetcher %s: %d results in %.1f ms",
                name,
                len(chunks),
                latency_ms,
            )

        return all_chunks, traces

"""
FetcherRegistry — keeps references to all available retrieval backends.

Fetchers are registered by name (matching FetcherName constants) and can be
looked up at runtime.  The LightRAG fetcher is a thin wrapper around the
LightRAGClient HTTP API so it fits the same AbstractFetcher interface.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..router.complexity_scorer import FetcherName
from .lightrag_adapter import LightRAGClient
from ..response.schema import RetrievalMethod

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# LightRAG wrapper — makes the HTTP client look like AbstractFetcher
# --------------------------------------------------------------------------- #

class LightRAGFetcher:
    """
    Wraps LightRAGClient to expose the same `.fetch(query, top_k)` interface
    as the data_module AbstractFetcher classes.

    Returned dicts are compatible with the internal RetrievedChunk format.
    """

    def __init__(self, client: LightRAGClient, mode: str = "hybrid") -> None:
        self._client = client
        self.mode = mode

    async def afetch(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        try:
            raw = await self._client.query(query, mode=self.mode, top_k=top_k)
        except Exception as exc:
            logger.error("LightRAGFetcher error: %s", exc)
            return []

        # LightRAG server returns {"response": "...", "context_items": [...]}
        # Normalise to our internal format
        context_items: list[dict[str, Any]] = raw.get("context_items") or []
        if not context_items and raw.get("response"):
            # Fallback: server returned synthesised text without context_items
            context_items = [
                {
                    "text": raw["response"],
                    "source": "lightrag",
                    "score": 0.5,
                }
            ]

        chunks = []
        for item in context_items[:top_k]:
            chunks.append(
                {
                    "chunk_id": item.get("id", ""),
                    "text": item.get("text", item.get("content", "")),
                    "score": float(item.get("score", 0.0)),
                    "source": item.get("source", "lightrag"),
                    "source_url": item.get("url", ""),
                    "retrieval_method": f"lightrag_{self.mode}",
                    "metadata": {k: v for k, v in item.items()},
                }
            )
        return chunks

    def fetch(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Sync wrapper — runs the coroutine in the current event loop."""
        return asyncio.get_event_loop().run_until_complete(self.afetch(query, top_k))


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

class FetcherRegistry:
    """
    Holds all active fetchers keyed by FetcherName constants.

    Populate at startup from your existing data_module fetchers::

        registry = FetcherRegistry()
        registry.register(FetcherName.FAST_RAG, fast_rag_fetcher_instance)
        registry.register(FetcherName.HYBRID, hybrid_fetcher_instance)
        registry.register(FetcherName.LIGHTRAG, LightRAGFetcher(lightrag_client))
    """

    def __init__(self) -> None:
        self._fetchers: dict[str, Any] = {}

    def register(self, name: str, fetcher: Any) -> None:
        self._fetchers[name] = fetcher
        logger.info("Registered fetcher: %s", name)

    def get(self, name: str) -> Any | None:
        return self._fetchers.get(name)

    def available(self) -> list[str]:
        return list(self._fetchers.keys())

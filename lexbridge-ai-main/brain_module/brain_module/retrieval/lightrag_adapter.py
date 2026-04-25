"""
LightRAGClient — async HTTP client that wraps the LightRAG server REST API.

LightRAGIngestionAdapter — converts CanonicalQA records → LightRAG insert format
and streams them into the running LightRAG server.

LightRAG server endpoints used:
  POST /insert         — ingest a single text document
  POST /query          — retrieve with mode=(naive|local|global|hybrid)
  GET  /health         — liveness check
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Thin async HTTP client
# --------------------------------------------------------------------------- #

class LightRAGClient:
    """
    Async wrapper around the LightRAG server REST API.

    Keeps a persistent httpx.AsyncClient for connection pooling.
    Caller is responsible for calling `.aclose()` (or using `async with`).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:9621",
        timeout: float = 60.0,
        api_key: str | None = None,
    ) -> None:
        timeout_env = os.getenv("LIGHTRAG_TIMEOUT_SECONDS")
        if timeout_env:
            try:
                timeout = float(timeout_env)
            except ValueError:
                logger.warning("Invalid LIGHTRAG_TIMEOUT_SECONDS=%r; using %.1fs", timeout_env, timeout)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers=headers,
        )

    async def health(self) -> bool:
        try:
            r = await self._client.get("/health")
            return r.status_code == 200
        except Exception:
            return False

    async def insert(self, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Insert a document into LightRAG's KG + vector store."""
        payload: dict[str, Any] = {"text": text}
        if metadata:
            payload["metadata"] = metadata
        r = await self._client.post("/insert", json=payload)
        r.raise_for_status()
        return r.json()

    async def insert_batch(
        self,
        documents: list[dict[str, Any]],
        *,
        concurrency: int = 4,
    ) -> list[dict[str, Any]]:
        """Insert multiple documents concurrently."""
        sem = asyncio.Semaphore(concurrency)

        async def _one(doc: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                return await self.insert(doc["text"], doc.get("metadata"))

        return await asyncio.gather(*[_one(d) for d in documents], return_exceptions=False)

    async def query(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
    ) -> dict[str, Any]:
        """
        Query LightRAG.

        Args:
            query: natural-language question.
            mode: one of "naive", "local", "global", "hybrid".
            top_k: number of context chunks to return.
        """
        payload = {"query": query, "mode": mode, "top_k": top_k}
        r = await self._client.post("/query", json=payload)
        r.raise_for_status()
        return r.json()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "LightRAGClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()


# --------------------------------------------------------------------------- #
# CanonicalQA → LightRAG ingestion adapter
# --------------------------------------------------------------------------- #

def canonical_qa_to_lightrag_doc(qa: Any) -> dict[str, Any]:
    """
    Convert a CanonicalQA dataclass/Pydantic model to the LightRAG insert payload.

    The text is formatted so that LightRAG's KG extractor sees a coherent passage:
      Q: <title>
      <body (first 500 chars)>
      Best Answer: <best answer body (first 800 chars)>
    """
    title: str = getattr(qa, "title", "") or ""
    body: str = getattr(qa, "body", "") or ""
    source_url: str = getattr(qa, "source_url", "") or ""

    source_val = getattr(qa, "source", None)
    source_name: str = source_val.value if source_val and hasattr(source_val, "value") else str(source_val or "")

    best_answer_body = ""
    best = getattr(qa, "best_answer", None)
    if callable(best):
        best = best()
    if best is not None:
        best_answer_body = getattr(best, "body", "") or ""

    text = (
        f"Q: {title}\n\n"
        f"{body[:500]}\n\n"
        f"Best Answer: {best_answer_body[:800]}"
    ).strip()

    metadata = {
        "source": source_name,
        "url": source_url,
        "canonical_id": getattr(qa, "id", ""),
        "tags": ",".join(getattr(qa, "tags", []) or []),
        "language": getattr(qa, "language", "en"),
    }

    return {"text": text, "metadata": metadata}


class LightRAGIngestionAdapter:
    """
    High-level adapter that streams CanonicalQA records into LightRAG.

    Usage::

        async with LightRAGClient() as client:
            adapter = LightRAGIngestionAdapter(client)
            await adapter.ingest_batch(qa_records, batch_size=20)
    """

    def __init__(self, client: LightRAGClient) -> None:
        self._client = client

    async def ingest_one(self, qa: Any) -> dict[str, Any]:
        doc = canonical_qa_to_lightrag_doc(qa)
        try:
            result = await self._client.insert(doc["text"], doc["metadata"])
            logger.debug("Ingested QA id=%s", doc["metadata"].get("canonical_id"))
            return result
        except Exception as exc:
            logger.error("Failed to ingest QA id=%s: %s", doc["metadata"].get("canonical_id"), exc)
            return {"error": str(exc)}

    async def ingest_batch(
        self,
        qa_records: list[Any],
        *,
        batch_size: int = 20,
        concurrency: int = 4,
    ) -> list[dict[str, Any]]:
        """Ingest records in batches with progress logging."""
        results: list[dict[str, Any]] = []
        total = len(qa_records)

        for start in range(0, total, batch_size):
            batch = qa_records[start : start + batch_size]
            docs = [canonical_qa_to_lightrag_doc(qa) for qa in batch]
            batch_results = await self._client.insert_batch(docs, concurrency=concurrency)
            results.extend(batch_results)
            logger.info(
                "LightRAG ingestion: %d/%d records done",
                min(start + batch_size, total),
                total,
            )

        return results

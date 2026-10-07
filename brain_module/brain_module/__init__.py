"""
brain_module — multi-source Q&A reasoning and synthesis layer.

Quick-start::

    from brain_module import BrainPipeline

    pipeline = BrainPipeline.from_env()
    response = await pipeline.ask("Why did the Roman Empire fall?")
    print(response.answer)
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from .aggregation import MultiSourceAggregator
from .cache.query_cache import QueryCache
from .reranking.cross_encoder import CrossEncoderReranker
from .response.formatter import ResponseFormatter
from .response.schema import BrainResponse
from .retrieval.fetcher_registry import FetcherRegistry, LightRAGFetcher
from .retrieval.lightrag_adapter import LightRAGClient
from .retrieval.parallel_runner import ParallelFetcher
from .router import QueryRouter
from .synthesis import SynthesisEngine
from .synthesis.llm_client import create_llm_client

__all__ = [
    "BrainPipeline",
    "BrainResponse",
    "ResponseFormatter",
    "QueryRouter",
    "FetcherRegistry",
    "LightRAGClient",
]


class BrainPipeline:
    """
    High-level façade for the full brain pipeline.

    Typical use::

        pipeline = await BrainPipeline.create(
            llm_backend="ollama",
            llm_model="qwen3:30b",
            lightrag_url="http://localhost:9621",
            fetchers={"fast_rag": my_fast_rag_fetcher},
        )
        response = await pipeline.ask("What is LightRAG?")
    """

    def __init__(
        self,
        registry: FetcherRegistry,
        router: QueryRouter,
        parallel_fetcher: ParallelFetcher,
        aggregator: MultiSourceAggregator,
        reranker: CrossEncoderReranker,
        synthesis_engine: SynthesisEngine,
        cache: QueryCache,
    ) -> None:
        self._registry = registry
        self._router = router
        self._parallel = parallel_fetcher
        self._aggregator = aggregator
        self._reranker = reranker
        self._synthesis = synthesis_engine
        self._cache = cache

    @classmethod
    async def create(
        cls,
        *,
        llm_backend: str = "ollama",
        llm_model: str | None = None,
        lightrag_url: str = "http://localhost:9621",
        reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        fetchers: dict[str, Any] | None = None,
        redis_url: str | None = None,
        semantic_dedup: bool = False,
        top_n_before_rerank: int = 50,
    ) -> "BrainPipeline":
        registry = FetcherRegistry()

        lightrag_client = LightRAGClient(base_url=lightrag_url)
        if await lightrag_client.health():
            registry.register("lightrag", LightRAGFetcher(lightrag_client, mode="hybrid"))

        for name, fetcher in (fetchers or {}).items():
            registry.register(name, fetcher)

        router = QueryRouter()
        parallel = ParallelFetcher(registry)
        aggregator = MultiSourceAggregator(
            semantic_dedup_threshold=0.92 if semantic_dedup else None,
            top_n_before_rerank=top_n_before_rerank,
        )
        reranker = CrossEncoderReranker(model_name=reranker_model)
        llm = create_llm_client(llm_backend, model=llm_model)
        synthesis = SynthesisEngine(llm_client=llm, reranker_model=reranker_model)
        cache = QueryCache(redis_url=redis_url)

        return cls(registry, router, parallel, aggregator, reranker, synthesis, cache)

    @classmethod
    def from_env(cls) -> "BrainPipeline":
        """Synchronous factory that reads config from environment variables."""
        return asyncio.get_event_loop().run_until_complete(
            cls.create(
                llm_backend=os.getenv("LLM_BACKEND", "ollama"),
                llm_model=os.getenv("LLM_MODEL"),
                lightrag_url=os.getenv("LIGHTRAG_URL", "http://localhost:9621"),
                reranker_model=os.getenv(
                    "RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
                ),
                redis_url=os.getenv("REDIS_URL"),
                semantic_dedup=os.getenv("SEMANTIC_DEDUP", "").lower() == "true",
            )
        )

    async def ask(
        self,
        question: str,
        *,
        top_k: int = 10,
        use_cache: bool = True,
        fetcher_override: list[str] | None = None,
    ) -> BrainResponse:
        t0 = time.perf_counter()

        if use_cache:
            cached = await self._cache.get(question)
            if cached:
                return cached  # type: ignore[return-value]

        plan = self._router.route(question)
        active = fetcher_override or plan.fetchers

        raw_chunks, traces = await self._parallel.run(question, active, top_k=top_k * 5)
        fused = self._aggregator.aggregate(raw_chunks, fetcher_weights=plan.weights)
        reranked = self._reranker.rerank(question, fused, top_k=top_k)
        latency_ms = (time.perf_counter() - t0) * 1000

        response = await self._synthesis.synthesise(
            question,
            reranked,
            retrieval_traces=traces,
            answer_type=plan.intent,
            latency_ms=latency_ms,
        )

        if use_cache:
            await self._cache.set(question, ResponseFormatter.to_dict(response))

        return response

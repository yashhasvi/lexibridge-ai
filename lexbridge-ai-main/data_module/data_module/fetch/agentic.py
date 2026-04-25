"""
Agentic RAG fetcher — tool-call-friendly multi-hop retrieval API.

Designed to be called by an LLM agent that can:
  1. Issue keyword + semantic searches
  2. Follow entity/question links (graph traversal)
  3. Ask for sub-questions to decompose complex queries
  4. Retrieve subgraph context for a specific entity

Each method is a discrete "tool" that an agent framework (LangChain, LlamaIndex,
custom function-calling) can register and invoke.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .base import AbstractFetcher, RetrievedChunk
from .fast_rag import FastRAGFetcher
from .graph_rag import GraphRAGFetcher
from .hybrid import HybridFetcher

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Accumulates retrieved evidence across multiple agent tool calls."""
    query: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    subgraph_contexts: list[str] = field(default_factory=list)
    call_log: list[dict[str, Any]] = field(default_factory=list)

    def add_chunks(self, new_chunks: list[RetrievedChunk], tool: str) -> None:
        seen = {c.chunk_id for c in self.chunks}
        for c in new_chunks:
            if c.chunk_id not in seen:
                self.chunks.append(c)
                seen.add(c.chunk_id)
        self.call_log.append({"tool": tool, "added": len(new_chunks)})

    def to_prompt_context(self, max_chunks: int = 8) -> str:
        """Render accumulated evidence as a context block for the LLM prompt."""
        blocks: list[str] = []
        if self.subgraph_contexts:
            blocks.append("\n".join(self.subgraph_contexts))
        for i, chunk in enumerate(self.chunks[:max_chunks]):
            blocks.append(f"[{i+1}] {chunk.to_context_str()}")
        return "\n\n---\n\n".join(blocks)


class AgenticFetcher:
    """
    Multi-tool fetcher for agentic RAG loops.

    Exposes discrete callable methods that an agent can use as tools:
      - semantic_search(query, top_k, filters)
      - keyword_search(query, top_k)
      - related_questions(question_id, depth)
      - entity_context(entity_id)
      - follow_duplicate(question_id)

    Usage (pseudo-agent loop):
        context = fetcher.new_context(original_query)
        context = fetcher.semantic_search(context, top_k=5)
        context = fetcher.related_questions(context, question_id=seeds[0].parent_question_id)
        prompt = context.to_prompt_context()
    """

    def __init__(
        self,
        fast_fetcher: FastRAGFetcher,
        graph_fetcher: GraphRAGFetcher,
        hybrid_fetcher: HybridFetcher | None = None,
    ) -> None:
        self.fast = fast_fetcher
        self.graph = graph_fetcher
        self.hybrid = hybrid_fetcher

    def new_context(self, query: str) -> AgentContext:
        return AgentContext(query=query)

    # ------------------------------------------------------------------
    # Tool 1: semantic search
    # ------------------------------------------------------------------
    def semantic_search(
        self,
        ctx: AgentContext,
        top_k: int = 8,
        source_filter: str | None = None,
        language_filter: str | None = None,
    ) -> AgentContext:
        """Dense semantic search for the context query."""
        results = self.fast.fetch(
            ctx.query,
            top_k=top_k,
            source_filter=source_filter,
            language_filter=language_filter,
        )
        ctx.add_chunks(results, tool="semantic_search")
        return ctx

    # ------------------------------------------------------------------
    # Tool 2: keyword search (BM25)
    # ------------------------------------------------------------------
    def keyword_search(
        self,
        ctx: AgentContext,
        top_k: int = 8,
        **kwargs: Any,
    ) -> AgentContext:
        """BM25 + dense hybrid search for the context query."""
        fetcher = self.hybrid or self.fast
        results = fetcher.fetch(ctx.query, top_k=top_k, **kwargs)
        ctx.add_chunks(results, tool="keyword_search")
        return ctx

    # ------------------------------------------------------------------
    # Tool 3: graph-expanded search
    # ------------------------------------------------------------------
    def graph_search(
        self,
        ctx: AgentContext,
        top_k: int = 8,
        seed_k: int = 3,
        **kwargs: Any,
    ) -> AgentContext:
        """Graph-augmented dense search: retrieves seeds + related questions."""
        results = self.graph.fetch(ctx.query, top_k=top_k, seed_k=seed_k, **kwargs)
        ctx.add_chunks(results, tool="graph_search")
        return ctx

    # ------------------------------------------------------------------
    # Tool 4: retrieve subgraph context for a specific question/entity
    # ------------------------------------------------------------------
    def entity_context(
        self,
        ctx: AgentContext,
        entity_id: str,
        depth: int = 1,
    ) -> AgentContext:
        """
        Retrieve the knowledge graph neighbourhood of a specific entity.
        Adds the subgraph as a text context block (not as chunks).
        """
        subgraph_text = self.graph.get_subgraph_context(entity_id, depth=depth)
        ctx.subgraph_contexts.append(subgraph_text)
        ctx.call_log.append({"tool": "entity_context", "entity_id": entity_id})
        return ctx

    # ------------------------------------------------------------------
    # Tool 5: follow DUPLICATE_OF links
    # ------------------------------------------------------------------
    def follow_duplicates(
        self,
        ctx: AgentContext,
        question_id: str,
        top_k: int = 3,
    ) -> AgentContext:
        """
        Find the canonical (non-duplicate) version of a question via graph traversal
        and retrieve its chunks.
        """
        try:
            subgraph = self.graph.graph_store.get_subgraph(question_id, depth=1)
            dup_ids = [
                t.object_id
                for t in subgraph.triples
                if t.predicate.value == "DUPLICATE_OF"
            ]
            for dup_id in dup_ids[:top_k]:
                rows = self.graph.lance_store.search(
                    query_vector=self.fast._embedder.encode([ctx.query])[0].tolist(),
                    top_k=1,
                    filters=f"parent_question_id = '{dup_id}'",
                )
                from .fast_rag import _row_to_chunk
                for row in rows:
                    ctx.add_chunks([_row_to_chunk(row)], tool="follow_duplicates")
        except Exception as exc:
            logger.warning("follow_duplicates failed for %s: %s", question_id, exc)
        return ctx

    # ------------------------------------------------------------------
    # Convenience: run a full multi-tool agent pass
    # ------------------------------------------------------------------
    def full_retrieval(
        self,
        query: str,
        top_k: int = 10,
        use_graph: bool = True,
        use_hybrid: bool = True,
    ) -> AgentContext:
        """
        Run the complete retrieval pipeline in a single call:
          1. Semantic search (fast dense)
          2. Keyword search (hybrid BM25+dense), if available
          3. Graph expansion, if enabled
        """
        ctx = self.new_context(query)
        ctx = self.semantic_search(ctx, top_k=top_k // 2)
        if use_hybrid and self.hybrid:
            ctx = self.keyword_search(ctx, top_k=top_k // 2)
        if use_graph and self.graph:
            ctx = self.graph_search(ctx, top_k=top_k // 2, seed_k=3)
        return ctx

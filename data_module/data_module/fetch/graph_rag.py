"""
Graph RAG fetcher — graph-augmented retrieval.

Strategy:
  1. Dense vector search to find seed chunks (fast_rag step).
  2. For each seed, look up the parent_question_id in the graph store.
  3. Expand 1-2 hops: retrieve related questions (RELATED_TO, DUPLICATE_OF),
     supporting answers (ANSWERS), and named entity context (MENTIONS).
  4. Fetch the expanded question chunks from LanceDB.
  5. Return seeds + expanded context as RetrievedChunks.

This gives the LLM richer multi-document context without needing
an explicit multi-hop query.
"""
from __future__ import annotations

import logging
from typing import Any

from ..storage.graph_store import AbstractStore as GraphStore
from ..storage.lance_store import LanceStore
from .base import AbstractFetcher, RetrievedChunk
from .fast_rag import FastRAGFetcher, _row_to_chunk

logger = logging.getLogger(__name__)


class GraphRAGFetcher(AbstractFetcher):
    """
    Graph-augmented retrieval: dense seed + graph subgraph expansion.

    Best for:
      - Multi-hop reasoning questions
      - Questions about related concepts
      - Agentic workflows needing richer context
    """

    def __init__(
        self,
        lance_store: LanceStore,
        graph_store: GraphStore,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str = "cpu",
        expand_depth: int = 1,
    ) -> None:
        self.fast_fetcher = FastRAGFetcher(lance_store, embedding_model, device)
        self.graph_store = graph_store
        self.lance_store = lance_store
        self.expand_depth = expand_depth

    def fetch(
        self,
        query: str,
        top_k: int = 10,
        seed_k: int = 5,
        **kwargs: Any,
    ) -> list[RetrievedChunk]:
        """
        Args:
            query: natural language query.
            top_k: total number of chunks to return (seeds + expanded).
            seed_k: number of initial seed chunks from dense search.
        """
        # Step 1: dense seed retrieval
        seeds = self.fast_fetcher.fetch(query, top_k=seed_k, **kwargs)
        if not seeds:
            return []

        seen_ids: set[str] = {s.chunk_id for s in seeds}
        expanded: list[RetrievedChunk] = list(seeds)

        # Step 2: graph expansion
        for seed in seeds:
            q_id = seed.parent_question_id
            if not q_id:
                continue

            try:
                subgraph = self.graph_store.get_subgraph(q_id, depth=self.expand_depth)
            except Exception as exc:
                logger.warning("Graph expansion failed for %s: %s", q_id, exc)
                continue

            # Collect related question IDs from the subgraph
            related_q_ids = [
                e.entity_id
                for e in subgraph.entities
                if e.entity_type == "question" and e.entity_id != q_id
            ]

            # Step 3: fetch those related questions from LanceDB
            for rel_id in related_q_ids[: top_k - len(expanded)]:
                if len(expanded) >= top_k:
                    break
                try:
                    rows = self.lance_store.search(
                        # Use the same vector — we want related, not re-ranked
                        query_vector=self.fast_fetcher._embedder.encode([query])[0].tolist(),
                        top_k=1,
                        filters=f"parent_question_id = '{rel_id}'",
                    )
                    for row in rows:
                        cid = row.get("chunk_id", "")
                        if cid not in seen_ids:
                            seen_ids.add(cid)
                            chunk = _row_to_chunk(row)
                            chunk.metadata["_expanded_from"] = q_id
                            expanded.append(chunk)
                except Exception:
                    pass

        return expanded[:top_k]

    def get_subgraph_context(self, question_id: str, depth: int = 1) -> str:
        """Return a text rendering of the graph neighbourhood for a question."""
        subgraph = self.graph_store.get_subgraph(question_id, depth=depth)
        return subgraph.to_context_str()

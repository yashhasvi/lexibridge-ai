"""data_module.fetch — retrieval API layer."""
from .base import AbstractFetcher, RetrievedChunk
from .fast_rag import FastRAGFetcher
from .graph_rag import GraphRAGFetcher
from .hybrid import HybridFetcher
from .agentic import AgenticFetcher, AgentContext

__all__ = [
    "AbstractFetcher",
    "RetrievedChunk",
    "FastRAGFetcher",
    "GraphRAGFetcher",
    "HybridFetcher",
    "AgenticFetcher",
    "AgentContext",
]

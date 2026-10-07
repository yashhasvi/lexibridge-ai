"""AbstractFetcher — base interface for all retrieval backends."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievedChunk:
    """A single retrieval result returned by any fetcher."""
    chunk_id: str
    text: str
    score: float
    source: str
    source_url: str = ""
    license: str = ""
    tags: list[str] = field(default_factory=list)
    chunk_type: str = ""
    parent_question_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_context_str(self) -> str:
        """Format as a context block suitable for LLM prompts."""
        lines = [f"[Source: {self.source} | Score: {self.score:.3f}]"]
        if self.source_url:
            lines.append(f"URL: {self.source_url}")
        lines.append(self.text)
        return "\n".join(lines)


class AbstractFetcher(ABC):
    @abstractmethod
    def fetch(self, query: str, top_k: int = 10, **kwargs) -> list[RetrievedChunk]:
        """Retrieve top_k results for a query string."""
        ...

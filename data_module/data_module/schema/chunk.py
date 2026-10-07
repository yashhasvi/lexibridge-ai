"""
ChunkRecord schema — the retrieval unit stored in the vector index.

Each CanonicalQA produces one or more ChunkRecords depending on chunking strategy.
ChunkRecords are what gets embedded and stored in LanceDB for RAG retrieval.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .provenance import ChunkType, License, SourceName


class ChunkMetadata(BaseModel):
    """
    Denormalized metadata stored alongside every chunk for filtering and display.
    Keeping metadata flat makes vector DB filters fast (no joins needed).
    """
    source: SourceName
    site: Optional[str] = None
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    score: int = 0
    view_count: Optional[int] = None
    has_accepted_answer: bool = False
    answer_count: int = 0
    license: License = License.UNKNOWN
    source_url: Optional[str] = None
    # Embedding versioning — allows safe reindex when model changes
    embedding_model: Optional[str] = None
    embedding_dim: Optional[int] = None
    chunking_policy: Optional[str] = None
    # Year bucket for time-based filtering (precomputed from created_at)
    year: Optional[int] = None


class ChunkRecord(BaseModel):
    """
    A single retrieval chunk stored in the vector index.

    Design decisions:
    - `chunk_id` is UUID; `parent_question_id` references CanonicalQA.id.
    - `text` is the raw text sent to the embedding model (title + body + answer).
    - `metadata` is fully denormalized so the vector DB needs no join for display.
    - `embedding` is stored here for serialization; the vector DB also indexes it.
    - `parent_chunk_id` enables hierarchical retrieval (child → parent expansion).
    """
    chunk_id: str
    parent_question_id: str
    parent_answer_id: Optional[str] = None
    parent_chunk_id: Optional[str] = None          # for hierarchical chunks

    chunk_type: ChunkType
    text: str                                       # text sent to embedding model
    token_count: int = 0

    metadata: ChunkMetadata

    # Populated by embedder stage
    embedding: Optional[list[float]] = None

    # Extra fields for multi-hop / agentic chunks
    supporting_fact_ids: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    def to_lance_row(self) -> dict[str, Any]:
        """Flatten to a dict suitable for LanceDB insertion."""
        row = {
            "chunk_id": self.chunk_id,
            "parent_question_id": self.parent_question_id,
            "parent_answer_id": self.parent_answer_id,
            "parent_chunk_id": self.parent_chunk_id,
            "chunk_type": self.chunk_type.value,
            "text": self.text,
            "token_count": self.token_count,
            "vector": self.embedding,
            # Flatten metadata for scalar filtering
            **{f"meta_{k}": v for k, v in self.metadata.model_dump().items()},
        }
        # Serialize list fields as JSON strings (LanceDB scalar filter friendly)
        if isinstance(row.get("meta_tags"), list):
            row["meta_tags"] = ",".join(row["meta_tags"])
        return row

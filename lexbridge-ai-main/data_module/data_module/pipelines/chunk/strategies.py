"""
Chunking strategies for CanonicalQA records.

Each strategy defines how a single CanonicalQA is split into one or more
ChunkRecords for embedding and vector index storage.

Strategies:
  canonical_qa    — one chunk = question title + body + best answer (default, fast RAG)
  per_answer      — one chunk per answer (more granular, better for multi-answer threads)
  multi_hop       — one chunk per supporting fact passage (for HotpotQA-style records)
  question_only   — question text only (for query-side indexing)
  hierarchical    — question_only chunk + per_answer chunks with parent_chunk_id links
"""
from __future__ import annotations

from enum import Enum
from typing import Generator
import uuid

from ...schema.canonical import CanonicalAnswer, CanonicalQA
from ...schema.chunk import ChunkMetadata, ChunkRecord
from ...schema.provenance import ChunkType


class Strategy(str, Enum):
    CANONICAL_QA = "canonical_qa"
    PER_ANSWER = "per_answer"
    MULTI_HOP = "multi_hop"
    QUESTION_ONLY = "question_only"
    HIERARCHICAL = "hierarchical"


def _make_metadata(record: CanonicalQA, extra: dict | None = None) -> ChunkMetadata:
    from datetime import datetime
    year = record.created_at.year if record.created_at else None
    return ChunkMetadata(
        source=record.source,
        site=record.site,
        language=record.language,
        tags=record.tags[:20],
        score=record.score,
        view_count=record.view_count,
        has_accepted_answer=record.accepted_answer_id is not None,
        answer_count=record.answer_count,
        license=record.license,
        source_url=record.source_url,
        year=year,
        **(extra or {}),
    )


def _chunk_id(text_key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"chunk:{text_key}"))


# ---------------------------------------------------------------------------
# canonical_qa: one chunk = title + body + best answer
# ---------------------------------------------------------------------------

def canonical_qa_strategy(record: CanonicalQA, max_tokens: int = 512) -> list[ChunkRecord]:
    best = record.best_answer
    parts = [f"Q: {record.title}"]
    if record.body and record.body != record.title:
        parts.append(record.body[:800])
    if best:
        parts.append(f"A: {best.body[:800]}")
    text = "\n\n".join(parts)

    return [
        ChunkRecord(
            chunk_id=_chunk_id(f"{record.id}:canonical"),
            parent_question_id=record.id,
            parent_answer_id=best.answer_id if best else None,
            chunk_type=ChunkType.CANONICAL_QA,
            text=text,
            token_count=len(text.split()),
            metadata=_make_metadata(record),
            supporting_fact_ids=[],
        )
    ]


# ---------------------------------------------------------------------------
# per_answer: one chunk per answer (includes question context)
# ---------------------------------------------------------------------------

def per_answer_strategy(record: CanonicalQA, max_tokens: int = 512) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    q_prefix = f"Q: {record.title}\n"
    for ans in record.sorted_answers:
        text = q_prefix + f"A: {ans.body[:800]}"
        chunks.append(
            ChunkRecord(
                chunk_id=_chunk_id(f"{record.id}:{ans.answer_id}:per_answer"),
                parent_question_id=record.id,
                parent_answer_id=ans.answer_id,
                chunk_type=ChunkType.ANSWER_ONLY,
                text=text,
                token_count=len(text.split()),
                metadata=_make_metadata(record),
            )
        )
    # If no answers, fall back to question-only chunk
    if not chunks:
        chunks = question_only_strategy(record)
    return chunks


# ---------------------------------------------------------------------------
# question_only: just the question, for query-side indexing
# ---------------------------------------------------------------------------

def question_only_strategy(record: CanonicalQA, max_tokens: int = 512) -> list[ChunkRecord]:
    text = f"Q: {record.title}\n{record.body[:800]}"
    return [
        ChunkRecord(
            chunk_id=_chunk_id(f"{record.id}:q_only"),
            parent_question_id=record.id,
            chunk_type=ChunkType.QUESTION_ONLY,
            text=text,
            token_count=len(text.split()),
            metadata=_make_metadata(record),
        )
    ]


# ---------------------------------------------------------------------------
# multi_hop: separate chunks for question + each supporting passage
# ---------------------------------------------------------------------------

def multi_hop_strategy(record: CanonicalQA, max_tokens: int = 512) -> list[ChunkRecord]:
    """
    For multi-hop QA (HotpotQA). Emits one canonical_qa chunk plus per-passage
    chunks with supporting_fact_ids linking them.
    """
    # Start with canonical chunk
    chunks = canonical_qa_strategy(record, max_tokens)
    parent_chunk_id = chunks[0].chunk_id if chunks else None

    # Extract supporting passages from body (stored after "\n\nSupporting context:\n")
    body = record.body
    marker = "\n\nSupporting context:\n"
    if marker in body:
        context_text = body.split(marker, 1)[1]
        passages = [p.strip() for p in context_text.split("\n") if p.strip()]
        for i, passage in enumerate(passages[:5]):  # cap at 5 passages
            text = f"Context [{i+1}]: {passage}"
            chunks.append(
                ChunkRecord(
                    chunk_id=_chunk_id(f"{record.id}:hop:{i}"),
                    parent_question_id=record.id,
                    parent_chunk_id=parent_chunk_id,
                    chunk_type=ChunkType.MULTI_HOP,
                    text=text,
                    token_count=len(text.split()),
                    metadata=_make_metadata(record),
                )
            )

    return chunks


# ---------------------------------------------------------------------------
# hierarchical: question_only parent + per_answer children
# ---------------------------------------------------------------------------

def hierarchical_strategy(record: CanonicalQA, max_tokens: int = 512) -> list[ChunkRecord]:
    """
    Builds a parent question chunk + child answer chunks with parent_chunk_id set.
    Enables hierarchical retrieval: child hit → expand to parent for full context.
    """
    parent = question_only_strategy(record, max_tokens)[0]
    children: list[ChunkRecord] = []
    for ans in record.sorted_answers:
        text = f"A: {ans.body[:800]}"
        children.append(
            ChunkRecord(
                chunk_id=_chunk_id(f"{record.id}:{ans.answer_id}:hier"),
                parent_question_id=record.id,
                parent_answer_id=ans.answer_id,
                parent_chunk_id=parent.chunk_id,
                chunk_type=ChunkType.ANSWER_ONLY,
                text=text,
                token_count=len(text.split()),
                metadata=_make_metadata(record),
            )
        )
    return [parent] + children


STRATEGY_MAP: dict[Strategy, object] = {
    Strategy.CANONICAL_QA: canonical_qa_strategy,
    Strategy.PER_ANSWER: per_answer_strategy,
    Strategy.QUESTION_ONLY: question_only_strategy,
    Strategy.MULTI_HOP: multi_hop_strategy,
    Strategy.HIERARCHICAL: hierarchical_strategy,
}

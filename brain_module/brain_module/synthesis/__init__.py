"""
SynthesisEngine — orchestrates prompt building → LLM call → citation validation
→ post-generation guardrails.

Takes re-ranked chunks and produces a BrainResponse with:
  - LLM-synthesised answer with inline [N] citations
  - SourceCard list (only cited sources)
  - Confidence score (mean re-ranker score of cited sources)
  - Guardrail flags surfaced from post-generation validation
"""
from __future__ import annotations

import logging
from typing import Any

from ..compression.sentence_compressor import SentenceCompressor
from ..guardrails.retrieval_filter import cap_source_diversity, filter_low_relevance, filter_score_gap
from ..guardrails.response_validator import validate_response
from ..response.schema import AnswerType, BrainResponse, RetrievalTrace, SourceCard
from .citation_parser import citations_to_source_cards, validate_citations
from .llm_client import LLMClient
from .prompt_builder import build_synthesis_prompt

logger = logging.getLogger(__name__)


def _chunks_to_source_cards(chunks: list[dict[str, Any]]) -> list[SourceCard]:
    """Convert normalised chunk dicts to SourceCard objects (1-based index)."""
    cards: list[SourceCard] = []
    for i, chunk in enumerate(chunks, start=1):
        cards.append(
            SourceCard(
                source_name=chunk.get("source") or "unknown",
                excerpt=chunk.get("text", "")[:600],
                url=chunk.get("source_url", ""),
                score=float(chunk.get("score", 0.0)),
                retrieval_method=chunk.get("retrieval_method", ""),
                chunk_id=chunk.get("chunk_id", ""),
                citation_index=i,
                metadata=chunk.get("metadata", {}),
            )
        )
    return cards


def _mean_score(source_cards: list[SourceCard]) -> float:
    if not source_cards:
        return 0.0
    return sum(s.score for s in source_cards) / len(source_cards)


class SynthesisEngine:
    """
    Usage::

        engine = SynthesisEngine(llm_client=create_llm_client("ollama"))
        brain_response = await engine.synthesise(
            question="Why did the Roman Empire fall?",
            reranked_chunks=top_chunks,
            retrieval_traces=traces,
            answer_type=QueryIntent.MULTI_HOP,
        )
    """

    def __init__(
        self,
        llm_client: LLMClient,
        reranker_model: str = "",
        max_synthesis_tokens: int = 1024,
        temperature: float = 0.2,
        top_k_for_synthesis: int = 4,
        *,
        min_rerank_score: float = 0.15,
        max_same_source: int = 2,
        low_confidence_threshold: float = 0.3,
        guardrail_strict_mode: bool = False,
        enable_llm_judge: bool = False,
        context_compressor: SentenceCompressor | None = None,
    ) -> None:
        self._llm = llm_client
        self._reranker_model = reranker_model
        self._max_tokens = max_synthesis_tokens
        self._temperature = temperature
        self._top_k = top_k_for_synthesis
        self._min_rerank_score = min_rerank_score
        self._max_same_source = max_same_source
        self._low_confidence_threshold = low_confidence_threshold
        self._guardrail_strict_mode = guardrail_strict_mode
        self._enable_llm_judge = enable_llm_judge
        self._compressor = context_compressor

    async def synthesise(
        self,
        question: str,
        reranked_chunks: list[dict[str, Any]],
        *,
        retrieval_traces: list[RetrievalTrace] | None = None,
        answer_type: Any = None,
        latency_ms: float = 0.0,
        top_k_override: int | None = None,
        max_tokens_override: int | None = None,
        enable_compression_override: bool | None = None,
    ) -> BrainResponse:
        """
        Build answer from top-K re-ranked chunks.

        Returns a BrainResponse even if the LLM call fails (error field is set).
        """
        top_k = self._top_k if top_k_override is None else max(1, int(top_k_override))
        max_tokens = (
            self._max_tokens if max_tokens_override is None else max(64, int(max_tokens_override))
        )
        compression_enabled = (
            self._compressor is not None
            if enable_compression_override is None
            else bool(enable_compression_override and self._compressor is not None)
        )

        top_chunks = reranked_chunks[:top_k]

        # --- Layer 1: retrieval guardrails ---
        top_chunks = filter_low_relevance(
            top_chunks, min_score=self._min_rerank_score, min_keep=1
        )
        top_chunks = filter_score_gap(top_chunks, max_gap_ratio=0.5, min_keep=1)
        top_chunks = cap_source_diversity(
            top_chunks, max_per_source=self._max_same_source
        )

        # --- Context compression (extractive sentence-level) ---
        if compression_enabled:
            top_chunks = self._compressor.compress(question, top_chunks)

        source_cards = _chunks_to_source_cards(top_chunks)

        if not source_cards:
            return BrainResponse(
                question=question,
                answer="I cannot answer this question — no relevant sources were retrieved.",
                sources=[],
                confidence=0.0,
                answer_type=AnswerType.UNANSWERABLE,
                retrieval_trace=retrieval_traces or [],
                latency_ms=latency_ms,
                error="no sources",
            )

        answer_type_str = ""
        if answer_type is not None:
            answer_type_str = str(answer_type.value if hasattr(answer_type, "value") else answer_type)

        avg_score = _mean_score(source_cards)

        source_blocks = [
            {
                "citation_index": s.citation_index,
                "source_name": s.source_name,
                "excerpt": s.excerpt,
                "score": s.score,
            }
            for s in source_cards
        ]

        # --- Layer 2: prompt guardrails (confidence hint) ---
        messages = build_synthesis_prompt(
            question,
            source_blocks,
            answer_type_hint=answer_type_str,
            confidence_hint=avg_score < self._low_confidence_threshold,
        )

        try:
            raw_answer, model_used = await self._llm.complete(
                messages,
                max_tokens=max_tokens,
                temperature=self._temperature,
            )
        except Exception as exc:
            logger.error("LLM synthesis failed: %s", exc)
            return BrainResponse(
                question=question,
                answer="Synthesis failed due to an LLM error.",
                sources=source_cards,
                confidence=avg_score,
                answer_type=_parse_answer_type(answer_type_str),
                retrieval_trace=retrieval_traces or [],
                latency_ms=latency_ms,
                model_used="",
                reranker_used=self._reranker_model,
                error=str(exc),
            )

        # Validate and clean citations
        cleaned_answer, invalid_refs = validate_citations(raw_answer, source_cards)
        if invalid_refs:
            logger.warning("LLM cited non-existent source indices: %s", invalid_refs)

        cited_cards = citations_to_source_cards(cleaned_answer, source_cards)
        if not cited_cards:
            cited_cards = source_cards

        # --- Layer 3: post-generation guardrails ---
        guardrail_flags: list[str] = []
        final_answer = cleaned_answer

        validation = validate_response(
            question,
            cleaned_answer,
            avg_rerank_score=avg_score,
            answer_type=answer_type_str,
            low_confidence_threshold=self._low_confidence_threshold,
            strict_mode=self._guardrail_strict_mode,
        )
        guardrail_flags = validation.issues

        if validation.modified_answer is not None:
            final_answer = validation.modified_answer

        # Optional LLM-as-judge (off by default)
        if self._enable_llm_judge and validation.passed:
            try:
                from ..guardrails.llm_judge import judge_response

                verdict = await judge_response(self._llm, question, final_answer)
                if not verdict.approved:
                    guardrail_flags.append("llm_judge_rejected")
                    final_answer = final_answer.rstrip() + (
                        "\n\nNote: This answer may not fully address the question. "
                        "Please verify the information."
                    )
            except Exception as exc:
                logger.warning("LLM judge error (fail-open): %s", exc)

        return BrainResponse(
            question=question,
            answer=final_answer,
            sources=cited_cards,
            confidence=round(_mean_score(cited_cards), 4),
            answer_type=_parse_answer_type(answer_type_str),
            retrieval_trace=retrieval_traces or [],
            latency_ms=latency_ms,
            model_used=model_used,
            reranker_used=self._reranker_model,
            guardrail_flags=guardrail_flags,
        )


def _parse_answer_type(hint: str) -> AnswerType:
    mapping = {
        "factual": AnswerType.FACTUAL,
        "multi_hop": AnswerType.MULTI_HOP,
        "opinion": AnswerType.OPINION,
        "unanswerable": AnswerType.UNANSWERABLE,
    }
    return mapping.get(hint.lower(), AnswerType.UNKNOWN)

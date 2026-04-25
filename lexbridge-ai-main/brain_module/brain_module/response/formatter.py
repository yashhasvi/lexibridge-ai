"""
ResponseFormatter — converts a BrainResponse to various output formats.

Supports:
  - dict / JSON (for API responses)
  - Markdown (for terminal / notebook display)
  - Plain text (stripped of citations for downstream tools)
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .schema import BrainResponse, SourceCard


class ResponseFormatter:
    """Stateless formatter; call class-methods directly."""

    @staticmethod
    def to_dict(response: BrainResponse) -> dict[str, Any]:
        """Pydantic-free dict suitable for JSON serialization."""
        return {
            "question": response.question,
            "answer": response.answer,
            "answer_type": response.answer_type.value,
            "confidence": round(response.confidence, 4),
            "latency_ms": round(response.latency_ms, 1),
            "model_used": response.model_used,
            "reranker_used": response.reranker_used,
            "sources": [
                {
                    "citation_index": s.citation_index,
                    "source_name": s.source_name,
                    "excerpt": s.excerpt,
                    "url": s.url,
                    "score": round(s.score, 4),
                    "retrieval_method": s.retrieval_method,
                    "chunk_id": s.chunk_id,
                    "metadata": s.metadata,
                }
                for s in response.sources
            ],
            "retrieval_trace": [
                {
                    "fetcher": t.fetcher,
                    "latency_ms": round(t.latency_ms, 1),
                    "results_returned": t.results_returned,
                    "error": t.error,
                }
                for t in response.retrieval_trace
            ],
            "error": response.error,
            "guardrail_flags": response.guardrail_flags,
        }

    @staticmethod
    def to_json(response: BrainResponse, indent: int = 2) -> str:
        return json.dumps(ResponseFormatter.to_dict(response), indent=indent, ensure_ascii=False)

    @staticmethod
    def to_markdown(response: BrainResponse) -> str:
        lines: list[str] = []

        lines.append(f"## Answer\n")
        lines.append(response.answer)
        lines.append("")

        if response.sources:
            lines.append("---\n### Sources\n")
            for s in response.sources:
                lines.append(f"**[{s.citation_index}] {s.source_name}** — score `{s.score:.3f}`")
                if s.url:
                    lines.append(f"> <{s.url}>")
                lines.append(f"> {s.excerpt[:300]}{'…' if len(s.excerpt) > 300 else ''}")
                lines.append("")

        meta: list[str] = [
            f"**Confidence:** {response.confidence:.3f}",
            f"**Answer type:** {response.answer_type.value}",
            f"**Model:** {response.model_used}",
            f"**Latency:** {response.latency_ms:.0f} ms",
        ]
        lines.append("---\n_" + " · ".join(meta) + "_")

        return "\n".join(lines)

    @staticmethod
    def to_plain_text(response: BrainResponse) -> str:
        """Strip all [N] citation markers — useful for downstream text processing."""
        import re
        return re.sub(r"\[\d+\]", "", response.answer).strip()

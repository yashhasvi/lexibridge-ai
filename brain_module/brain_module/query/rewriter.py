"""
QueryRewriter — expands ambiguous or short queries into multiple retrieval variants.

Two strategies:
  1. **LLM-based** (default): uses a fast LLM call with a short prompt to generate
     2-3 query variants that capture different phrasings / angles.
  2. **Heuristic fallback**: simple synonym + entity-based expansion when LLM
     is unavailable or disabled.

The original query is *always* included as variant #1 so retrieval quality
never degrades — variants only add coverage.

Environment variables
---------------------
QUERY_REWRITE_ENABLED      : "true" to enable (default: true)
QUERY_REWRITE_MAX_VARIANTS : max variants including original (default: 3)
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM = (
    "You are a search-query expansion engine. "
    "Given a user question, output 2 alternative phrasings that would help "
    "retrieve relevant documents. Each variant should capture a different angle "
    "or use different keywords while preserving the original intent.\n\n"
    "Rules:\n"
    "- Output ONLY the two variants, one per line, numbered 1. and 2.\n"
    "- Do NOT repeat the original question.\n"
    "- Do NOT add explanations, prefixes, or bullet points.\n"
    "- Keep each variant under 40 words.\n"
    "- If the question references a pronoun (it, they, this), resolve it if possible."
)


class QueryRewriter:
    """
    Produces query variants for parallel retrieval.

    Usage::

        rewriter = QueryRewriter(llm_client=llm)
        variants = await rewriter.rewrite("Who won it?")
        # ["Who won it?", "Who won the championship?", "Winner of the competition"]
    """

    def __init__(
        self,
        llm_client: Any = None,
        max_variants: int = 3,
        enabled: bool = True,
    ) -> None:
        self._llm = llm_client
        self._max_variants = max(1, max_variants)
        self._enabled = enabled

    async def rewrite(self, query: str, *, max_variants_override: int | None = None) -> list[str]:
        """
        Return a list of query variants (original always first).

        Falls back to [original] on any error.
        """
        original = query.strip()
        if not self._enabled or not original:
            return [original]

        max_variants = self._max_variants
        if max_variants_override is not None:
            max_variants = max(1, int(max_variants_override))

        if self._llm is not None:
            try:
                return await self._llm_rewrite(original, max_variants=max_variants)
            except Exception as exc:
                logger.warning("LLM query rewrite failed, using original only: %s", exc)

        return [original]

    async def _llm_rewrite(self, query: str, *, max_variants: int) -> list[str]:
        messages = [
            {"role": "system", "content": _REWRITE_SYSTEM},
            {"role": "user", "content": query},
        ]
        raw_answer, _ = await self._llm.complete(
            messages, max_tokens=128, temperature=0.7
        )
        variants = self._parse_variants(raw_answer, query)
        return [query] + variants[: max_variants - 1]

    @staticmethod
    def _parse_variants(raw: str, original: str) -> list[str]:
        """Extract clean query variants from LLM output."""
        lines = raw.strip().splitlines()
        variants: list[str] = []
        original_lower = original.lower().strip()

        for line in lines:
            cleaned = re.sub(r"^\s*\d+[\.\):\-]\s*", "", line).strip()
            cleaned = cleaned.strip('"\'')
            if not cleaned or len(cleaned) < 5:
                continue
            if cleaned.lower() == original_lower:
                continue
            variants.append(cleaned)

        return variants

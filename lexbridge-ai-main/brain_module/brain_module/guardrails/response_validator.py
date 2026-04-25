"""
Post-generation guardrails — heuristic checks on the LLM answer.

All checks are lightweight (regex / keyword overlap) with zero extra LLM calls.

Checks:
  1. Negative-lead detection    Flags answers starting with "X is not …"
  2. Self-contradiction scan    Detects "A is X … but A is not X" patterns
  3. Answer-question alignment  Ensures the first sentence relates to the question
  4. Confidence gate            Low reranker score + flagged issues → disclaimer / fallback
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_NEGATIVE_LEAD_RE = re.compile(
    r"^\s*(?:"
    r"(?:no\s*,)|"
    r"(?:that\s+is\s+(?:not|incorrect|wrong))|"
    r"(?:\w[\w\s]{0,40}\s+(?:is|are|was|were)\s+not\s+)"
    r")",
    re.IGNORECASE,
)

_CONTRADICTION_RE = re.compile(
    r"(?P<subj>\b\w[\w\s]{0,30}?)\s+(?:is|are)\s+(?:not\s+)?(?P<claim>\w[\w\s]{0,30}?)"
    r"[.,;]\s*(?:but|however|although|yet)\s+"
    r"(?P=subj)\s+(?:is|are)\s+(?:not\s+)?",
    re.IGNORECASE,
)

_CITATION_RE = re.compile(r"\[\d+\]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_LOW_CONFIDENCE_DISCLAIMER = (
    "\n\nNote: This answer is based on limited source material and may not be fully accurate."
)
_UNANSWERABLE_FALLBACK = (
    "I cannot confidently answer this based on the available sources."
)


@dataclass
class ValidationResult:
    """Outcome of running all post-generation guardrail checks."""
    passed: bool
    issues: list[str] = field(default_factory=list)
    suggested_action: str = "pass"  # "pass" | "disclaimer" | "fallback"
    modified_answer: str | None = None


def _first_sentence(text: str) -> str:
    """Extract the first sentence from *text*, stripping citation markers."""
    clean = _CITATION_RE.sub("", text).strip()
    parts = _SENTENCE_SPLIT_RE.split(clean, maxsplit=1)
    return parts[0] if parts else clean


def _extract_keywords(text: str, min_len: int = 3) -> set[str]:
    """Return lowercased words of length >= *min_len*, ignoring stopwords."""
    stopwords = {
        "the", "and", "for", "are", "but", "not", "you", "all", "can", "has",
        "her", "was", "one", "our", "out", "his", "how", "its", "may", "who",
        "did", "get", "him", "had", "what", "does", "this", "that", "with",
        "from", "they", "been", "have", "said", "each", "which", "their",
        "will", "other", "about", "many", "then", "them", "some", "would",
        "into", "than", "more", "these", "such", "where", "when", "most",
        "also", "based", "according", "sources", "source", "using",
    }
    words = set(re.findall(r"\b[a-zA-Z]{%d,}\b" % min_len, text.lower()))
    return words - stopwords


def check_negative_lead(answer: str) -> bool:
    """Return True if the answer starts with a negative / contradictory framing."""
    return bool(_NEGATIVE_LEAD_RE.match(answer))


def check_self_contradiction(answer: str) -> bool:
    """Return True if the answer contains an obvious self-contradiction pattern."""
    return bool(_CONTRADICTION_RE.search(answer))


def check_answer_question_alignment(
    question: str,
    answer: str,
    min_overlap: int = 1,
) -> bool:
    """
    Return True if the first sentence of the answer shares at least
    *min_overlap* meaningful keywords with the question.
    """
    q_kw = _extract_keywords(question)
    first = _first_sentence(answer)
    a_kw = _extract_keywords(first)
    overlap = q_kw & a_kw
    return len(overlap) >= min_overlap


def validate_response(
    question: str,
    answer: str,
    *,
    avg_rerank_score: float = 1.0,
    answer_type: str = "unknown",
    low_confidence_threshold: float = 0.3,
    very_low_confidence_threshold: float = 0.10,
    strict_mode: bool = False,
) -> ValidationResult:
    """
    Run all heuristic guardrail checks on *answer* and return a
    :class:`ValidationResult` with any issues found and a suggested action.

    Args:
        question:       the original user question.
        answer:         the LLM-generated answer text (post citation-cleanup).
        avg_rerank_score: mean cross-encoder score of cited sources.
        answer_type:    intent classification string (e.g. "factual").
        low_confidence_threshold:  score below which a disclaimer is appended.
        very_low_confidence_threshold: score below which the answer may be replaced.
        strict_mode:    if True, replace rather than disclaim on guardrail failures.
    """
    issues: list[str] = []

    is_factual = answer_type in ("factual", "unknown")

    if is_factual and check_negative_lead(answer):
        issues.append("negative_lead")

    if check_self_contradiction(answer):
        issues.append("self_contradiction")

    if is_factual and not check_answer_question_alignment(question, answer):
        issues.append("low_alignment")

    low_conf = avg_rerank_score < low_confidence_threshold
    very_low_conf = avg_rerank_score < very_low_confidence_threshold

    if not issues and not low_conf:
        return ValidationResult(passed=True, issues=[], suggested_action="pass")

    action = "pass"
    modified: str | None = None

    if very_low_conf and issues:
        action = "fallback"
        modified = _UNANSWERABLE_FALLBACK
    elif issues and strict_mode:
        action = "fallback"
        modified = _UNANSWERABLE_FALLBACK
    elif low_conf and issues:
        action = "disclaimer"
        modified = answer.rstrip() + _LOW_CONFIDENCE_DISCLAIMER
    elif issues:
        action = "disclaimer"
        modified = answer.rstrip() + _LOW_CONFIDENCE_DISCLAIMER
    elif low_conf:
        action = "pass"

    passed = action == "pass"

    if issues:
        logger.warning(
            "Guardrail issues detected: %s (score=%.3f, action=%s)",
            issues, avg_rerank_score, action,
        )

    return ValidationResult(
        passed=passed,
        issues=issues,
        suggested_action=action,
        modified_answer=modified,
    )

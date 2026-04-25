"""
Optional LLM-as-judge — second-pass validation using a lightweight LLM call.

Gated behind ``ENABLE_LLM_JUDGE=true`` (off by default) to avoid extra
latency and cost in the default pipeline.

When enabled, the judge asks the same LLM (or a cheaper model) a short
yes/no question about the answer's quality.  If it says NO, the caller
can retry with a tightened prompt or attach a disclaimer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..synthesis.llm_client import LLMClient

logger = logging.getLogger(__name__)

_JUDGE_SYSTEM = (
    "You are a strict quality-assurance reviewer for a question-answering system. "
    "You evaluate whether an answer directly and correctly addresses the question "
    "without internal contradictions."
)

_JUDGE_USER_TEMPLATE = """\
Question: {question}

Answer: {answer}

Does this answer directly and correctly address the question without contradiction?
Reply with exactly YES or NO on the first line, followed by a one-sentence reason.\
"""


@dataclass
class JudgeVerdict:
    """Result of the LLM-as-judge evaluation."""
    approved: bool
    reason: str
    raw_output: str


async def judge_response(
    llm: "LLMClient",
    question: str,
    answer: str,
    *,
    max_tokens: int = 128,
    temperature: float = 0.0,
) -> JudgeVerdict:
    """
    Ask the LLM to evaluate whether *answer* correctly addresses *question*.

    Returns a :class:`JudgeVerdict` with the boolean outcome and reason.
    Failures are caught and treated as approval (fail-open) to avoid
    blocking the user on judge errors.
    """
    messages = [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {
            "role": "user",
            "content": _JUDGE_USER_TEMPLATE.format(
                question=question, answer=answer
            ),
        },
    ]

    try:
        raw, _ = await llm.complete(
            messages, max_tokens=max_tokens, temperature=temperature
        )
    except Exception as exc:
        logger.warning("LLM judge call failed (fail-open): %s", exc)
        return JudgeVerdict(approved=True, reason="judge_error", raw_output=str(exc))

    first_line = raw.strip().split("\n", 1)[0].strip().upper()
    approved = not first_line.startswith("NO")
    reason = raw.strip().split("\n", 1)[1].strip() if "\n" in raw.strip() else ""

    logger.info("LLM judge verdict: approved=%s reason=%s", approved, reason[:120])

    return JudgeVerdict(approved=approved, reason=reason, raw_output=raw)

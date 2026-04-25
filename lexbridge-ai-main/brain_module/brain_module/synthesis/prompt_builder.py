"""
PromptBuilder — constructs the multi-source citation prompt for the LLM.

The prompt enforces:
  - [N] inline citations tied to numbered source blocks
  - Conflict notation when sources disagree
  - An "I don't know" escape hatch if sources are insufficient
"""
from __future__ import annotations

from typing import Any

_SYSTEM_PROMPT = """\
You are a precise question-answering assistant.

CRITICAL RULES:
1. Answer the question DIRECTLY in your FIRST sentence. State the answer, then cite with [N].
2. ONLY use sources that directly answer the question. SKIP any source that is about a different topic.
3. Do NOT mention or discuss sources that are irrelevant to the question — pretend they do not exist.
4. Do NOT start your answer with what something is NOT.
5. If multiple sources agree, cite all: [1][3].
6. If sources contradict each other on the answer, note the disagreement.
7. If no source answers the question, say "I cannot answer this based on the available sources."
8. Do NOT add information beyond what the sources say.
9. Keep answers SHORT. One to two sentences for simple factual questions.\
"""


def build_synthesis_prompt(
    question: str,
    source_blocks: list[dict[str, Any]],
    *,
    answer_type_hint: str = "",
    confidence_hint: bool = False,
) -> list[dict[str, str]]:
    """
    Build the message list for the LLM chat API.

    Args:
        question:        the user's question.
        source_blocks:   list of dicts with keys:
                         citation_index (int), source_name (str), excerpt (str), score (float)
        answer_type_hint: optional hint e.g. "multi_hop" to adjust instructions.
        confidence_hint:  if True, inject a note warning that sources may have
                         limited relevance (triggered when avg reranker score is low).

    Returns:
        OpenAI-style messages: [{"role": ..., "content": ...}, ...]
    """
    sources_text = _format_sources(source_blocks)

    extra_instruction = ""
    if answer_type_hint == "factual":
        extra_instruction = (
            "\nThis is a simple factual question. Reply in 1-2 sentences MAX. "
            "ONLY mention the direct answer. Do NOT discuss other sources or tangential facts."
        )
    elif answer_type_hint == "multi_hop":
        extra_instruction = (
            "\nThis question requires reasoning across multiple sources. "
            "Synthesise the evidence into a coherent explanation."
        )
    elif answer_type_hint == "technical":
        extra_instruction = (
            "\nFor technical questions, include exact terms, commands, or code "
            "excerpts from the sources where relevant."
        )

    confidence_note = ""
    if confidence_hint:
        confidence_note = (
            "\nNote: The retrieved sources may have limited relevance to this question. "
            "Only answer if you find a clear, direct answer in the sources."
        )

    user_content = (
        f"Sources:\n{sources_text}\n\n"
        f"Question: {question}{extra_instruction}{confidence_note}\n\n"
        f"Answer (use [N] citations):"
    )

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _format_sources(source_blocks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for s in source_blocks:
        idx = s.get("citation_index", "?")
        name = s.get("source_name", "unknown")
        score = s.get("score", 0.0)
        excerpt = s.get("excerpt", "")[:600]
        lines.append(f"[{idx}] {name} (score {score:.2f}):\n{excerpt}")
    return "\n\n".join(lines)

"""
CitationParser — extracts [N] inline citation markers from the LLM answer
and maps them back to SourceCard objects.

Also validates that every cited index exists in the source list, and
removes orphaned citation markers from the final answer text.
"""
from __future__ import annotations

import re
from typing import Any

_CITATION_RE = re.compile(r"\[(\d+)\]")


def extract_cited_indices(answer: str) -> list[int]:
    """Return sorted list of unique citation indices found in `answer`."""
    found = {int(m) for m in _CITATION_RE.findall(answer)}
    return sorted(found)


def validate_citations(
    answer: str,
    source_cards: list[Any],
    *,
    remove_invalid: bool = True,
) -> tuple[str, list[int]]:
    """
    Check that every [N] in `answer` maps to a valid source card.

    Args:
        answer:         synthesised answer from LLM.
        source_cards:   list of SourceCard objects (1-based citation_index).
        remove_invalid: strip [N] markers for out-of-range N from the text.

    Returns:
        (cleaned_answer, list_of_invalid_indices)
    """
    valid_indices = {s.citation_index for s in source_cards}
    cited = extract_cited_indices(answer)
    invalid = [i for i in cited if i not in valid_indices]

    cleaned = answer
    if remove_invalid and invalid:
        pattern = re.compile(r"\[(" + "|".join(str(i) for i in invalid) + r")\]")
        cleaned = pattern.sub("", cleaned).strip()

    return cleaned, invalid


def citations_to_source_cards(
    answer: str,
    source_cards: list[Any],
) -> list[Any]:
    """
    Return only the SourceCards that are actually cited in `answer`.
    Preserves citation_index values.
    """
    cited = set(extract_cited_indices(answer))
    return [s for s in source_cards if s.citation_index in cited]

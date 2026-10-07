"""
SourceGrouper — groups chunks by source_name for downstream display.

Useful for the ResponseFormatter to show "3 results from Stack Overflow,
2 from Wikipedia" etc., and for the synthesis prompt to reference each
source coherently.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def group_by_source(
    chunks: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Return chunks grouped by their `source` field."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        source = chunk.get("source") or "unknown"
        groups[source].append(chunk)
    return dict(groups)


def source_summary(groups: dict[str, list[dict[str, Any]]]) -> str:
    parts = [f"{len(v)} from {k}" for k, v in sorted(groups.items())]
    return ", ".join(parts)

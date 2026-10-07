"""
Ingest loader — drives source.iter_canonical() and feeds downstream stages.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator

from ...schema.canonical import CanonicalQA
from ...sources import SOURCE_REGISTRY, AbstractDataSource

logger = logging.getLogger(__name__)


def get_source(
    name: str, raw_dir: Path, source_config: dict
) -> AbstractDataSource:
    """Instantiate a source connector by name."""
    cls = SOURCE_REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown source '{name}'. Available: {list(SOURCE_REGISTRY.keys())}"
        )
    return cls(raw_dir / name, source_config)


def load_source(
    name: str,
    raw_dir: Path,
    source_config: dict,
    limit: int = 0,
) -> Generator[CanonicalQA, None, None]:
    """Download and parse a source, yielding CanonicalQA records."""
    source = get_source(name, raw_dir, source_config)
    logger.info("Loading source: %s (limit=%s)", name, limit or "unlimited")
    yield from source.iter_canonical(limit=limit)

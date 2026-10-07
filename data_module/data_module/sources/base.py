"""
AbstractDataSource — base class all source connectors must implement.

Each source module must provide:
  - downloader.py  — fetches raw data files from the internet
  - parser.py      — reads raw files into dicts/rows
  - mapper.py      — converts raw dicts to CanonicalQA records

The three concerns are separated so the pipeline can:
  1. Download once and cache raw files.
  2. Re-parse without re-downloading.
  3. Re-map (e.g. after schema changes) without re-parsing.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generator

from ..schema.canonical import CanonicalQA

logger = logging.getLogger(__name__)


class AbstractDownloader(ABC):
    """Downloads raw source files to a local directory."""

    def __init__(self, raw_dir: Path, config: dict) -> None:
        self.raw_dir = raw_dir
        self.config = config
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def download(self) -> list[Path]:
        """Download source files. Returns list of downloaded file paths."""
        ...

    def is_downloaded(self) -> bool:
        """Return True if raw files already exist (skip re-download)."""
        return any(self.raw_dir.iterdir()) if self.raw_dir.exists() else False


class AbstractParser(ABC):
    """Reads raw files and yields dicts (source-specific structure)."""

    def __init__(self, raw_dir: Path, config: dict) -> None:
        self.raw_dir = raw_dir
        self.config = config

    @abstractmethod
    def parse(self) -> Generator[dict, None, None]:
        """Yield raw dicts from downloaded files."""
        ...


class AbstractMapper(ABC):
    """Maps source-specific raw dicts to CanonicalQA records."""

    def __init__(self, config: dict) -> None:
        self.config = config

    @abstractmethod
    def map(self, raw: dict) -> CanonicalQA | None:
        """
        Convert a raw dict to a CanonicalQA.
        Return None to skip the record (e.g. failed validation, below min score).
        """
        ...


class AbstractDataSource(ABC):
    """
    Orchestrates downloader + parser + mapper for a single source.
    The pipeline's loader calls `iter_canonical()` which chains all three.
    """

    name: str  # must match SourceName enum value

    def __init__(self, raw_dir: Path, config: dict) -> None:
        self.raw_dir = raw_dir
        self.config = config

    @property
    @abstractmethod
    def downloader(self) -> AbstractDownloader:
        ...

    @property
    @abstractmethod
    def parser(self) -> AbstractParser:
        ...

    @property
    @abstractmethod
    def mapper(self) -> AbstractMapper:
        ...

    def iter_canonical(self, limit: int = 0) -> Generator[CanonicalQA, None, None]:
        """
        Full pipeline: download → parse → map → yield CanonicalQA.

        Args:
            limit: if > 0, stop after this many records (useful for testing).
        """
        if not self.downloader.is_downloaded():
            logger.info("[%s] Downloading raw files…", self.name)
            self.downloader.download()
        else:
            logger.info("[%s] Raw files already present, skipping download.", self.name)

        count = 0
        for raw in self.parser.parse():
            record = self.mapper.map(raw)
            if record is None:
                continue
            yield record
            count += 1
            if limit and count >= limit:
                logger.info("[%s] Reached limit of %d records.", self.name, limit)
                break

        logger.info("[%s] Yielded %d records.", self.name, count)

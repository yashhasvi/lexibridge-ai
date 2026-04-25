"""Stack Exchange data source — wires downloader, parser, and mapper."""
from __future__ import annotations

from pathlib import Path
from typing import Generator

from ..base import AbstractDataSource, AbstractDownloader, AbstractMapper, AbstractParser
from ...schema.canonical import CanonicalQA
from .downloader import StackExchangeDownloader
from .parser import StackExchangeParser
from .mapper import StackExchangeMapper


class StackExchangeSource(AbstractDataSource):
    name = "stackexchange"

    def __init__(self, raw_dir: Path, config: dict) -> None:
        super().__init__(raw_dir, config)
        self._downloader = StackExchangeDownloader(raw_dir, config)
        self._parser = StackExchangeParser(raw_dir, config)
        self._mapper = StackExchangeMapper(config)

    @property
    def downloader(self) -> AbstractDownloader:
        return self._downloader

    @property
    def parser(self) -> AbstractParser:
        return self._parser

    @property
    def mapper(self) -> AbstractMapper:
        return self._mapper

    def iter_canonical(self, limit: int = 0) -> Generator[CanonicalQA, None, None]:
        """Override to use the two-pass map_stream (needed to join answers to questions)."""
        import logging
        logger = logging.getLogger(__name__)

        if not self._downloader.is_downloaded():
            logger.info("[%s] Downloading raw files…", self.name)
            self._downloader.download()

        raw_stream = self._parser.parse()
        count = 0
        for record in self._mapper.map_stream(raw_stream):
            yield record
            count += 1
            if limit and count >= limit:
                break
        logger.info("[%s] Yielded %d records.", self.name, count)

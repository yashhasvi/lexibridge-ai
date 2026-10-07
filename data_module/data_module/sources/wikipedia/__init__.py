"""
Wikipedia source — article text from Wikimedia XML dumps.

Uses the `datasets` library's wikipedia dataset for simplicity,
falling back to direct dump parsing via WikiExtractor for full control.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Generator

from ..base import AbstractDataSource, AbstractDownloader, AbstractMapper, AbstractParser
from ..hf_base import HFDownloader, HFParser
from ...schema.canonical import CanonicalAnswer, CanonicalQA
from ...schema.provenance import License, SourceName


class WikipediaMapper(AbstractMapper):
    """Maps Wikipedia article rows to CanonicalQA (passage-as-answer format)."""

    def map(self, raw: dict) -> CanonicalQA | None:
        try:
            title = (raw.get("title") or "").strip()
            text = (raw.get("text") or "").strip()
            article_id = str(raw.get("id", ""))
            url = raw.get("url", f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}")

            min_len = self.config.get("min_article_length", 200)
            if len(text) < min_len:
                return None

            # Store article as a "question" (title) + "answer" (article text)
            # This makes Wikipedia passages retrievable in the same index as QA
            answer = CanonicalAnswer(
                answer_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"wiki:body:{article_id}")),
                body=text[:4000],  # cap at 4k chars; chunker will split further
                score=1,
                is_accepted=True,
            )

            return CanonicalQA(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"wiki:{article_id}")),
                source=SourceName.WIKIPEDIA,
                source_id=article_id,
                title=title,
                body=text[:4000],
                answers=[answer],
                accepted_answer_id=answer.answer_id,
                tags=[],
                language=self.config.get("language", "en"),
                score=0,
                source_url=url,
                license=License.CC_BY_SA_40,
            )
        except Exception:
            return None


class WikipediaSource(AbstractDataSource):
    """
    Downloads Wikipedia via Hugging Face `datasets` (wikimedia/wikipedia).
    Config should set huggingface_id = "wikimedia/wikipedia" and config = "20231101.en".
    """
    name = "wikipedia"

    def __init__(self, raw_dir: Path, config: dict) -> None:
        # Provide defaults for HF loader
        config.setdefault("huggingface_id", "wikimedia/wikipedia")
        config.setdefault("config", "20231101.en")
        config.setdefault("splits", ["train"])
        super().__init__(raw_dir, config)
        self._downloader = HFDownloader(raw_dir, config)
        self._parser = HFParser(raw_dir, config)
        self._mapper = WikipediaMapper(config)

    @property
    def downloader(self) -> AbstractDownloader:
        return self._downloader

    @property
    def parser(self) -> AbstractParser:
        return self._parser

    @property
    def mapper(self) -> AbstractMapper:
        return self._mapper

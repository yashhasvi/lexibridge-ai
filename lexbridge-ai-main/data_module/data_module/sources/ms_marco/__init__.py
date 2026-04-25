"""MS MARCO source — passage-level QA pairs."""
from __future__ import annotations

import uuid
from pathlib import Path

from ..base import AbstractDataSource, AbstractDownloader, AbstractMapper, AbstractParser
from ..hf_base import HFDownloader, HFParser
from ...schema.canonical import CanonicalAnswer, CanonicalQA
from ...schema.provenance import License, SourceName


class MSMARCOMapper(AbstractMapper):
    def map(self, raw: dict) -> CanonicalQA | None:
        try:
            qid = str(raw.get("query_id", raw.get("id", "")))
            query = (raw.get("query") or "").strip()
            if not query:
                return None

            # MS MARCO answers/passages come back as numpy.ndarray from Parquet
            # (not plain list) — normalise to list before any boolean checks.
            def _to_list(val) -> list:
                if val is None:
                    return []
                if isinstance(val, list):
                    return val
                try:
                    return list(val)   # numpy ndarray, pandas Series, etc.
                except Exception:
                    return []

            answers_raw = raw.get("answers", [])
            if isinstance(answers_raw, dict):
                answers_raw = answers_raw.get("value", [])
            answers_raw = [a for a in _to_list(answers_raw) if a and a != "No Answer Present."]

            if not answers_raw and self.config.get("only_has_answer", True):
                return None

            min_len = self.config.get("min_answer_length", 5)
            canonical_answers = []
            for text in answers_raw:
                if len(str(text)) >= min_len:
                    canonical_answers.append(
                        CanonicalAnswer(
                            answer_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"marco:{qid}:{str(text)[:50]}")),
                            body=str(text),
                            score=1,
                            is_accepted=True,
                        )
                    )

            # Build body from passages context
            passages_raw = raw.get("passages", {})
            passage_texts: list[str] = []
            if isinstance(passages_raw, dict):
                passage_texts = _to_list(passages_raw.get("passage_text", []))
            elif isinstance(passages_raw, list):
                passage_texts = [p.get("passage_text", "") if isinstance(p, dict) else str(p) for p in passages_raw]
            body = query
            if passage_texts:
                body += "\n\nPassages:\n" + "\n---\n".join(str(p) for p in passage_texts[:3])

            return CanonicalQA(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"marco:{qid}")),
                source=SourceName.MS_MARCO,
                source_id=qid,
                title=query,
                body=body,
                answers=canonical_answers,
                accepted_answer_id=canonical_answers[0].answer_id if canonical_answers else None,
                language="en",
                score=1,
                source_url="https://microsoft.github.io/msmarco/",
                license=License.CC_BY_40,
            )
        except Exception:
            return None


class MSMARCOSource(AbstractDataSource):
    name = "ms_marco"

    def __init__(self, raw_dir: Path, config: dict) -> None:
        super().__init__(raw_dir, config)
        self._downloader = HFDownloader(raw_dir, config)
        self._parser = HFParser(raw_dir, config)
        self._mapper = MSMARCOMapper(config)

    @property
    def downloader(self) -> AbstractDownloader:
        return self._downloader

    @property
    def parser(self) -> AbstractParser:
        return self._parser

    @property
    def mapper(self) -> AbstractMapper:
        return self._mapper

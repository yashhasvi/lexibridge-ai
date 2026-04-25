"""SQuAD 2.0 source — reading comprehension QA over Wikipedia paragraphs."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Generator

from ..base import AbstractDataSource, AbstractDownloader, AbstractMapper, AbstractParser
from ..hf_base import HFDownloader, HFParser
from ...schema.canonical import CanonicalAnswer, CanonicalQA
from ...schema.provenance import License, SourceName


class SQuADMapper(AbstractMapper):
    def map(self, raw: dict) -> CanonicalQA | None:
        try:
            qid = raw.get("id", "")
            question = raw.get("question", "").strip()
            context = raw.get("context", "").strip()
            title = raw.get("title", "")

            if not question:
                return None

            # SQuAD answers: dict with 'text' list and 'answer_start' list
            answers_dict = raw.get("answers", {})
            answer_texts = answers_dict.get("text", []) if isinstance(answers_dict, dict) else []
            include_unanswerable = self.config.get("include_unanswerable", True)

            if not answer_texts and not include_unanswerable:
                return None

            canonical_answers = []
            seen = set()
            for text in answer_texts:
                if text and text not in seen:
                    seen.add(text)
                    canonical_answers.append(
                        CanonicalAnswer(
                            answer_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"squad:{qid}:{text}")),
                            body=text,
                            score=1,
                            is_accepted=True,
                        )
                    )

            # Prepend context as the question body for RAG retrieval
            body = f"{question}\n\nContext: {context}" if context else question

            return CanonicalQA(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"squad:{qid}")),
                source=SourceName.SQUAD,
                source_id=qid,
                title=question,
                body=body,
                answers=canonical_answers,
                accepted_answer_id=canonical_answers[0].answer_id if canonical_answers else None,
                tags=[title] if title else [],
                language="en",
                score=1,
                source_url="https://rajpurkar.github.io/SQuAD-explorer/",
                license=License.CC_BY_SA_40,
            )
        except Exception:
            return None


class SQuADSource(AbstractDataSource):
    name = "squad"

    def __init__(self, raw_dir: Path, config: dict) -> None:
        super().__init__(raw_dir, config)
        self._downloader = HFDownloader(raw_dir, config)
        self._parser = HFParser(raw_dir, config)
        self._mapper = SQuADMapper(config)

    @property
    def downloader(self) -> AbstractDownloader:
        return self._downloader

    @property
    def parser(self) -> AbstractParser:
        return self._parser

    @property
    def mapper(self) -> AbstractMapper:
        return self._mapper

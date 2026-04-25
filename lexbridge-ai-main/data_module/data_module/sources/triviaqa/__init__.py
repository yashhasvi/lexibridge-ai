"""TriviaQA source — trivia QA pairs with Wikipedia/web evidence documents."""
from __future__ import annotations

import uuid
from pathlib import Path

from ..base import AbstractDataSource, AbstractDownloader, AbstractMapper, AbstractParser
from ..hf_base import HFDownloader, HFParser
from ...schema.canonical import CanonicalAnswer, CanonicalQA
from ...schema.provenance import License, SourceName


class TriviaQAMapper(AbstractMapper):
    def map(self, raw: dict) -> CanonicalQA | None:
        try:
            qid = str(raw.get("question_id", ""))
            question = (raw.get("question") or "").strip()
            if not question:
                return None

            def _to_list(val) -> list:
                """Safely convert numpy ndarray or other array-like to list."""
                if val is None:
                    return []
                if isinstance(val, list):
                    return val
                try:
                    return list(val)
                except Exception:
                    return []

            # Answer can be dict with 'value', 'aliases', 'normalized_value'
            answer_raw = raw.get("answer", {})
            if isinstance(answer_raw, dict):
                answer_text = answer_raw.get("value", "")
                aliases = _to_list(answer_raw.get("aliases", []))
            else:
                answer_text = str(answer_raw)
                aliases = []

            answer_text = (answer_text or "").strip()
            canonical_answers = []
            if answer_text:
                canonical_answers.append(
                    CanonicalAnswer(
                        answer_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"trivia:{qid}:{answer_text}")),
                        body=answer_text,
                        score=1,
                        is_accepted=True,
                    )
                )

            # Build body using evidence pages
            include_evidence = self.config.get("include_evidence", True)
            body = question
            if include_evidence:
                entity_pages = raw.get("entity_pages", {})
                if isinstance(entity_pages, dict):
                    wiki_contexts = _to_list(entity_pages.get("wiki_context", []))
                    if wiki_contexts:
                        body += "\n\nEvidence:\n" + str(wiki_contexts[0])[:500]

            tags = [str(a) for a in aliases[:5]]

            return CanonicalQA(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"trivia:{qid}")),
                source=SourceName.TRIVIAQA,
                source_id=qid,
                title=question,
                body=body,
                answers=canonical_answers,
                accepted_answer_id=canonical_answers[0].answer_id if canonical_answers else None,
                tags=tags,
                language="en",
                score=1,
                source_url="https://nlp.cs.washington.edu/triviaqa/",
                license=License.APACHE_20,
            )
        except Exception:
            return None


class TriviaQASource(AbstractDataSource):
    name = "triviaqa"

    def __init__(self, raw_dir: Path, config: dict) -> None:
        super().__init__(raw_dir, config)
        self._downloader = HFDownloader(raw_dir, config)
        self._parser = HFParser(raw_dir, config)
        self._mapper = TriviaQAMapper(config)

    @property
    def downloader(self) -> AbstractDownloader:
        return self._downloader

    @property
    def parser(self) -> AbstractParser:
        return self._parser

    @property
    def mapper(self) -> AbstractMapper:
        return self._mapper

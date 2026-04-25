"""HotpotQA source — multi-hop reasoning QA requiring two Wikipedia paragraphs."""
from __future__ import annotations

import uuid
from pathlib import Path

from ..base import AbstractDataSource, AbstractDownloader, AbstractMapper, AbstractParser
from ..hf_base import HFDownloader, HFParser
from ...schema.canonical import CanonicalAnswer, CanonicalQA
from ...schema.provenance import License, SourceName


class HotpotQAMapper(AbstractMapper):
    def map(self, raw: dict) -> CanonicalQA | None:
        try:
            qid = str(raw.get("id", ""))
            question = (raw.get("question") or "").strip()
            if not question:
                return None

            answer_text = (raw.get("answer") or "").strip()
            level = raw.get("level", "")
            q_type = raw.get("type", "")

            include_levels = self.config.get("include_levels", [])
            if include_levels and level not in include_levels:
                return None

            # Build body: question + supporting facts context
            context_raw = raw.get("context", {})
            supporting_facts_raw = raw.get("supporting_facts", {})

            context_titles: list[str] = []
            context_sentences: list[str] = []
            if isinstance(context_raw, dict):
                context_titles = context_raw.get("title", [])
                sents = context_raw.get("sentences", [])
                # sents is list of lists
                for sent_list in sents:
                    if isinstance(sent_list, list):
                        context_sentences.extend(sent_list)
            elif isinstance(context_raw, list):
                for item in context_raw:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        context_titles.append(item[0])
                        if isinstance(item[1], list):
                            context_sentences.extend(item[1])

            body = question
            if context_sentences:
                body += "\n\nSupporting context:\n" + " ".join(context_sentences[:10])

            canonical_answers = []
            if answer_text:
                canonical_answers.append(
                    CanonicalAnswer(
                        answer_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"hotpot:{qid}:{answer_text}")),
                        body=answer_text,
                        score=1,
                        is_accepted=True,
                    )
                )

            return CanonicalQA(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"hotpot:{qid}")),
                source=SourceName.HOTPOTQA,
                source_id=qid,
                title=question,
                body=body,
                answers=canonical_answers,
                accepted_answer_id=canonical_answers[0].answer_id if canonical_answers else None,
                tags=list(filter(None, [level, q_type])),
                language="en",
                score=1,
                related_ids=context_titles,  # Wikipedia titles as related refs
                source_url="https://hotpotqa.github.io",
                license=License.CC_BY_SA_40,
                extra={"level": level, "type": q_type},
            )
        except Exception:
            return None


class HotpotQASource(AbstractDataSource):
    name = "hotpotqa"

    def __init__(self, raw_dir: Path, config: dict) -> None:
        super().__init__(raw_dir, config)
        self._downloader = HFDownloader(raw_dir, config)
        self._parser = HFParser(raw_dir, config)
        self._mapper = HotpotQAMapper(config)

    @property
    def downloader(self) -> AbstractDownloader:
        return self._downloader

    @property
    def parser(self) -> AbstractParser:
        return self._parser

    @property
    def mapper(self) -> AbstractMapper:
        return self._mapper

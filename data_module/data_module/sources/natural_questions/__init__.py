"""Natural Questions source — real Google search queries + Wikipedia answers."""
from __future__ import annotations

import uuid
from pathlib import Path

from ..base import AbstractDataSource, AbstractDownloader, AbstractMapper, AbstractParser
from ..hf_base import HFDownloader, HFParser
from ...schema.canonical import CanonicalAnswer, CanonicalQA
from ...schema.provenance import License, SourceName


def _to_list(val) -> list:
    """Robustly convert numpy arrays, lists, or other iterables to a plain list."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    try:
        import numpy as np
        if isinstance(val, np.ndarray):
            return val.tolist()
    except ImportError:
        pass
    try:
        return list(val)
    except Exception:
        return []


class NQMapper(AbstractMapper):
    def map(self, raw: dict) -> CanonicalQA | None:
        try:
            qid = str(raw.get("id", ""))
            question = ""

            # NQ structure varies between simplified and full versions
            if isinstance(raw.get("question"), dict):
                question = raw["question"].get("text", "")
            elif isinstance(raw.get("question"), str):
                question = raw["question"]

            question = question.strip()
            if not question:
                return None

            # Extract short answers from annotations (full NQ — short_answers are numpy arrays)
            annotations = raw.get("annotations", {})
            short_answers: list[str] = []

            if isinstance(annotations, dict):
                sa_list = _to_list(annotations.get("short_answers", []))
                for sa in sa_list:
                    if not isinstance(sa, dict):
                        continue
                    texts = _to_list(sa.get("text", []))
                    for t in texts:
                        if t and str(t).strip():
                            short_answers.append(str(t).strip())
            elif isinstance(annotations, list):
                for ann in annotations:
                    if isinstance(ann, dict):
                        for sa in _to_list(ann.get("short_answers", [])):
                            if isinstance(sa, dict):
                                for t in _to_list(sa.get("text", [])):
                                    if t and str(t).strip():
                                        short_answers.append(str(t).strip())

            include_no_answer = bool(self.config.get("include_no_answer", False))
            if not short_answers and not include_no_answer:
                return None

            canonical_answers = []
            for text in dict.fromkeys(short_answers):  # deduplicate preserving order
                if text:
                    canonical_answers.append(
                        CanonicalAnswer(
                            answer_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"nq:{qid}:{text}")),
                            body=text,
                            score=1,
                            is_accepted=True,
                        )
                    )

            return CanonicalQA(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"nq:{qid}")),
                source=SourceName.NATURAL_QUESTIONS,
                source_id=qid,
                title=question,
                body=question,
                answers=canonical_answers,
                accepted_answer_id=canonical_answers[0].answer_id if canonical_answers else None,
                language="en",
                score=1,
                source_url="https://ai.google.com/research/NaturalQuestions",
                license=License.CC_BY_SA_30,
            )
        except Exception:
            return None


class NaturalQuestionsSource(AbstractDataSource):
    name = "natural_questions"

    def __init__(self, raw_dir: Path, config: dict) -> None:
        super().__init__(raw_dir, config)
        self._downloader = HFDownloader(raw_dir, config)
        self._parser = HFParser(raw_dir, config)
        self._mapper = NQMapper(config)

    @property
    def downloader(self) -> AbstractDownloader:
        return self._downloader

    @property
    def parser(self) -> AbstractParser:
        return self._parser

    @property
    def mapper(self) -> AbstractMapper:
        return self._mapper

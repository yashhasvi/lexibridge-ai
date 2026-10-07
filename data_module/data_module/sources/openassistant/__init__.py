"""
OpenAssistant OASST2 source — multi-turn human conversation trees.

The dataset is structured as message trees. We reconstruct full conversation
threads and emit one CanonicalQA per (prompter_root, best_assistant_response) pair.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from pathlib import Path
from typing import Generator

from ..base import AbstractDataSource, AbstractDownloader, AbstractMapper, AbstractParser
from ..hf_base import HFDownloader, HFParser
from ...schema.canonical import CanonicalAnswer, CanonicalQA
from ...schema.provenance import License, SourceName


class OASSMapper(AbstractMapper):
    """
    Two-pass mapper: buffer all messages by tree_id, then emit Q+A pairs.
    Emits the root prompter message as the question and the top-ranked
    assistant reply as the accepted answer.
    """

    def map(self, raw: dict) -> CanonicalQA | None:
        # Single-row map not meaningful for OASS; use map_stream.
        return None

    def map_stream(
        self, raw_rows: Generator[dict, None, None]
    ) -> Generator[CanonicalQA, None, None]:
        include_langs = set(self.config.get("include_languages", []))
        min_quality = self.config.get("min_quality_score", 0.0)
        max_toxicity = self.config.get("max_toxicity_score", 1.0)

        trees: dict[str, list[dict]] = defaultdict(list)
        for row in raw_rows:
            lang = row.get("lang", "en")
            if include_langs and lang not in include_langs:
                continue
            tree_id = row.get("message_tree_id", "")
            trees[tree_id].append(row)

        for tree_id, messages in trees.items():
            record = self._build_from_tree(tree_id, messages, min_quality, max_toxicity)
            if record:
                yield record

    def _build_from_tree(
        self,
        tree_id: str,
        messages: list[dict],
        min_quality: float,
        max_toxicity: float,
    ) -> CanonicalQA | None:
        try:
            # Find root prompter message
            roots = [m for m in messages if m.get("parent_id") is None and m.get("role") == "prompter"]
            if not roots:
                return None
            root = roots[0]

            question_text = (root.get("text") or "").strip()
            if not question_text:
                return None

            lang = root.get("lang", "en")
            root_id = root.get("message_id", "")

            # Find direct assistant replies to this root
            replies = [
                m for m in messages
                if m.get("parent_id") == root_id and m.get("role") == "assistant"
            ]

            canonical_answers = []
            for reply in replies:
                text = (reply.get("text") or "").strip()
                if not text:
                    continue
                labels = reply.get("labels", {}) or {}
                quality = labels.get("quality", {})
                toxicity = labels.get("toxicity", {})
                q_score = quality.get("value", 1.0) if isinstance(quality, dict) else 1.0
                t_score = toxicity.get("value", 0.0) if isinstance(toxicity, dict) else 0.0
                if q_score < min_quality or t_score > max_toxicity:
                    continue
                rank = reply.get("rank", 99)
                canonical_answers.append(
                    CanonicalAnswer(
                        answer_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"oasst:{reply.get('message_id', '')}")),
                        body=text,
                        score=int((1 - rank / max(len(replies), 1)) * 100),
                        is_accepted=(rank == 0),
                        created_at=None,
                    )
                )
            canonical_answers.sort(key=lambda a: (-a.is_accepted, -a.score))

            return CanonicalQA(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"oasst:{tree_id}")),
                source=SourceName.OPENASSISTANT,
                source_id=tree_id,
                title=question_text[:200],
                body=question_text,
                answers=canonical_answers,
                accepted_answer_id=canonical_answers[0].answer_id if canonical_answers else None,
                tags=[lang],
                language=lang,
                score=len(canonical_answers),
                source_url="https://huggingface.co/datasets/OpenAssistant/oasst2",
                license=License.APACHE_20,
            )
        except Exception:
            return None


class OpenAssistantSource(AbstractDataSource):
    name = "openassistant"

    def __init__(self, raw_dir: Path, config: dict) -> None:
        super().__init__(raw_dir, config)
        self._downloader = HFDownloader(raw_dir, config)
        self._parser = HFParser(raw_dir, config)
        self._mapper = OASSMapper(config)

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
        import logging
        logger = logging.getLogger(__name__)
        if not self._downloader.is_downloaded():
            self._downloader.download()
        count = 0
        for record in self._mapper.map_stream(self._parser.parse()):
            yield record
            count += 1
            if limit and count >= limit:
                break
        logger.info("[oasst] Yielded %d records.", count)

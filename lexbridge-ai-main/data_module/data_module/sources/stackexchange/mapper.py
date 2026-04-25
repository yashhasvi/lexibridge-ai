"""
Stack Exchange mapper — converts raw post dicts to CanonicalQA records.

Two-pass strategy:
  Pass 1: buffer all answers keyed by ParentId.
  Pass 2: emit one CanonicalQA per question, attaching its answers.

For large dumps (stackoverflow ~60M rows) this is streamed in batches
to avoid loading everything into memory at once.
"""
from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Generator

from ...schema.canonical import CanonicalAnswer, CanonicalQA
from ...schema.provenance import License, SourceName
from ..base import AbstractMapper

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<([^>]+)>")


def _parse_tags(tag_str: str) -> list[str]:
    """Parse SE tag string '<python><pandas>' → ['python', 'pandas']."""
    return _TAG_RE.findall(tag_str) if tag_str else []


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.rstrip("Z"))
    except ValueError:
        return None


def _license_for_site(_site: str) -> License:
    # All SE content in the April 2024 dump is CC BY-SA 4.0
    return License.CC_BY_SA_40


class StackExchangeMapper(AbstractMapper):
    """
    Buffers raw post dicts per site, then yields CanonicalQA records.

    Usage: feed all rows from the parser into `map_stream()` rather than
    calling `map()` row-by-row (answers must be matched to their questions).
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._min_q_score: int = config.get("min_question_score", -5)
        self._min_a_score: int = config.get("min_answer_score", -3)

    def map(self, raw: dict) -> CanonicalQA | None:
        """
        Single-record map — only works for question rows already enriched with answers.
        Use `map_stream()` for full raw streams.
        """
        if raw.get("PostTypeId") != "1":
            return None
        return self._build_question(raw, answers=raw.get("_answers", []))

    def map_stream(
        self, raw_rows: Generator[dict, None, None]
    ) -> Generator[CanonicalQA, None, None]:
        """
        Two-pass stream mapper: buffers answers, then emits questions.
        Partitioned by site to keep memory bounded.
        """
        questions_by_site: dict[str, dict[str, dict]] = defaultdict(dict)
        answers_by_site: dict[str, dict[str, list[dict]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for row in raw_rows:
            if row.get("_record_type") == "post_link":
                continue
            site = row.get("_site", "unknown")
            post_type = row.get("PostTypeId")
            if post_type == "1":
                questions_by_site[site][row["Id"]] = row
            elif post_type == "2":
                parent = row.get("ParentId", "")
                answers_by_site[site][parent].append(row)

        for site, questions in questions_by_site.items():
            for qid, q_row in questions.items():
                answers = answers_by_site[site].get(qid, [])
                record = self._build_question(q_row, answers)
                if record is not None:
                    yield record

    def _build_question(
        self, q_row: dict, answers: list[dict]
    ) -> CanonicalQA | None:
        try:
            score = int(q_row.get("Score", 0))
            if score < self._min_q_score:
                return None

            site = q_row.get("_site", "unknown")
            qid = q_row["Id"]
            accepted_id = q_row.get("AcceptedAnswerId")

            canonical_answers = []
            for a_row in answers:
                a_score = int(a_row.get("Score", 0))
                if a_score < self._min_a_score:
                    continue
                canonical_answers.append(
                    CanonicalAnswer(
                        answer_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"se:{site}:{a_row['Id']}")),
                        body=a_row.get("Body", ""),
                        body_html=a_row.get("Body"),
                        score=a_score,
                        is_accepted=(a_row["Id"] == accepted_id),
                        author_id=a_row.get("OwnerUserId"),
                        created_at=_parse_dt(a_row.get("CreationDate")),
                    )
                )
            # Sort: accepted first, then by score
            canonical_answers.sort(key=lambda a: (not a.is_accepted, -a.score))

            canonical_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"se:{site}:{qid}"))
            accepted_canonical_id = None
            if accepted_id:
                for a in canonical_answers:
                    if a.is_accepted:
                        accepted_canonical_id = a.answer_id
                        break

            return CanonicalQA(
                id=canonical_id,
                source=SourceName.STACKEXCHANGE,
                source_id=qid,
                site=site,
                title=q_row.get("Title", ""),
                body=q_row.get("Body", ""),
                body_html=q_row.get("Body"),
                answers=canonical_answers,
                accepted_answer_id=accepted_canonical_id,
                tags=_parse_tags(q_row.get("Tags", "")),
                language="en",
                score=score,
                view_count=int(q_row["ViewCount"]) if q_row.get("ViewCount") else None,
                answer_count=int(q_row.get("AnswerCount", len(canonical_answers))),
                created_at=_parse_dt(q_row.get("CreationDate")),
                updated_at=_parse_dt(q_row.get("LastEditDate")),
                source_url=f"https://{site}.com/q/{qid}",
                license=_license_for_site(site),
            )
        except Exception as exc:
            logger.warning("[SE] Failed to map question %s: %s", q_row.get("Id"), exc)
            return None

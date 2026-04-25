"""
Transform normalizer — strips HTML and cleans text in CanonicalQA records.

Operates in-place on a stream of CanonicalQA records and returns new
(immutable) records with cleaned body/answer text.
"""
from __future__ import annotations

import logging
import re
import unicodedata
import warnings
from typing import Generator

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

from ...schema.canonical import CanonicalAnswer, CanonicalQA


_WHITESPACE_RE = re.compile(r"\s{2,}")
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _strip_html(html: str) -> str:
    """Remove HTML tags, decode entities, preserve code blocks as plain text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    # Replace <code>/<pre> with backtick fences before stripping
    for tag in soup.find_all(["pre", "code"]):
        tag.replace_with(f"\n```\n{tag.get_text()}\n```\n")
    text = soup.get_text(separator=" ")
    return text


def _normalize(text: str, strip_html: bool = True, normalize_whitespace: bool = True) -> str:
    """Full normalization pipeline for a single text field."""
    if strip_html:
        text = _strip_html(text)
    # Normalize unicode (NFC)
    text = unicodedata.normalize("NFC", text)
    if normalize_whitespace:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Collapse runs of spaces/tabs (but keep newlines for structure)
        lines = [_WHITESPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
        text = "\n".join(line for line in lines if line)
    return text.strip()


class Normalizer:
    """
    Applies HTML stripping and text normalization to a stream of CanonicalQA records.
    Produces new CanonicalQA objects (does not mutate in-place).
    """

    def __init__(
        self,
        strip_html: bool = True,
        normalize_whitespace: bool = True,
        min_text_length: int = 20,
    ) -> None:
        self.strip_html = strip_html
        self.normalize_whitespace = normalize_whitespace
        self.min_text_length = min_text_length

    def normalize(self, record: CanonicalQA) -> CanonicalQA | None:
        """Normalize a single record. Returns None if text is too short after cleaning."""
        clean_body = _normalize(record.body, self.strip_html, self.normalize_whitespace)
        if len(clean_body) < self.min_text_length:
            return None

        clean_answers = []
        for ans in record.answers:
            clean_ans_body = _normalize(ans.body, self.strip_html, self.normalize_whitespace)
            if not clean_ans_body:
                continue
            clean_answers.append(
                ans.model_copy(update={"body": clean_ans_body})
            )

        return record.model_copy(
            update={
                "body": clean_body,
                "answers": clean_answers,
                # Keep body_html for provenance; it's the original
            }
        )

    def normalize_stream(
        self,
        records: Generator[CanonicalQA, None, None],
        log_every: int = 10000,
    ) -> Generator[CanonicalQA, None, None]:
        count = 0
        for record in records:
            result = self.normalize(record)
            if result is not None:
                yield result
                count += 1
                if count % log_every == 0:
                    logger.info("[normalizer] Normalized %d records…", count)

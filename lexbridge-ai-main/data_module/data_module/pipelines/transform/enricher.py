"""
Transform enricher — NER and entity linking on CanonicalQA records.

Pipeline:
  1. spaCy NER on title + body → EntityMention objects (surface form + type)
  2. (Optional) Entity linking: match surface forms against Wikidata entity index
     using fuzzy string matching (exact match on label first, then alias lookup).

Entity linking is disabled by default until the Wikidata index is built.
"""
from __future__ import annotations

import logging
from typing import Generator

from ...schema.canonical import CanonicalQA, EntityMention

logger = logging.getLogger(__name__)

# spaCy entity types we care about (skip CARDINAL, PERCENT, etc.)
_USEFUL_ENTITY_TYPES = {
    "PERSON", "ORG", "GPE", "LOC", "PRODUCT", "EVENT",
    "WORK_OF_ART", "LAW", "LANGUAGE", "NORP", "FAC",
}


class Enricher:
    """
    Adds NER entity mentions to CanonicalQA records.

    Lazy-loads spaCy model on first use so import is fast.
    """

    def __init__(
        self,
        spacy_model: str = "en_core_web_sm",
        run_ner: bool = True,
        run_entity_linking: bool = False,
        wikidata_index: dict[str, str] | None = None,  # label → wikidata_id
    ) -> None:
        self.spacy_model = spacy_model
        self.run_ner = run_ner
        self.run_entity_linking = run_entity_linking
        self.wikidata_index = wikidata_index or {}
        self._nlp = None

    def _get_nlp(self):
        if self._nlp is None:
            import spacy
            try:
                self._nlp = spacy.load(self.spacy_model, disable=["parser", "lemmatizer"])
            except OSError:
                logger.warning(
                    "spaCy model '%s' not found. Run: python -m spacy download %s",
                    self.spacy_model,
                    self.spacy_model,
                )
                self._nlp = None
        return self._nlp

    def enrich(self, record: CanonicalQA) -> CanonicalQA:
        if not self.run_ner:
            return record

        nlp = self._get_nlp()
        if nlp is None:
            return record

        # Run NER on title + first 500 chars of body
        text = f"{record.title}. {record.body[:500]}"
        doc = nlp(text)

        mentions: list[EntityMention] = []
        seen_surface = set()
        for ent in doc.ents:
            if ent.label_ not in _USEFUL_ENTITY_TYPES:
                continue
            surface = ent.text.strip()
            if not surface or surface in seen_surface:
                continue
            seen_surface.add(surface)

            wikidata_id = None
            confidence = 0.0
            if self.run_entity_linking and self.wikidata_index:
                wikidata_id = self.wikidata_index.get(surface.lower())
                confidence = 1.0 if wikidata_id else 0.0

            mentions.append(
                EntityMention(
                    surface_form=surface,
                    entity_type=ent.label_,
                    start_char=ent.start_char,
                    end_char=ent.end_char,
                    wikidata_id=wikidata_id,
                    confidence=confidence,
                )
            )

        return record.model_copy(update={"entity_mentions": mentions})

    def enrich_stream(
        self,
        records: Generator[CanonicalQA, None, None],
        log_every: int = 5000,
        batch_size: int = 64,
        n_process: int = 1,
    ) -> Generator[CanonicalQA, None, None]:
        """
        Enrich a stream of records using spaCy's batched nlp.pipe() for speed.

        Args:
            batch_size: texts per spaCy batch (64-128 is optimal for en_core_web_sm).
            n_process:  CPU cores for spaCy multiprocessing (set > 1 to go faster;
                        on macOS use n_process=1 and rely on batch_size alone to
                        avoid fork-related issues with the spaCy model).
        """
        if not self.run_ner:
            yield from records
            return

        nlp = self._get_nlp()
        if nlp is None:
            yield from records
            return

        # Buffer records so we can zip them back with their docs after nlp.pipe()
        record_buffer: list[CanonicalQA] = []
        texts: list[str] = []
        count = 0          # counts entity mentions extracted
        records_done = 0   # counts records yielded (for progress logging)

        def _flush() -> Generator[CanonicalQA, None, None]:
            nonlocal count, records_done
            for rec, doc in zip(record_buffer, nlp.pipe(texts, batch_size=batch_size, n_process=n_process)):
                mentions: list = []
                seen_surface: set[str] = set()
                for ent in doc.ents:
                    if ent.label_ not in _USEFUL_ENTITY_TYPES:
                        continue
                    surface = ent.text.strip()
                    if not surface or surface in seen_surface:
                        continue
                    seen_surface.add(surface)
                    wikidata_id = None
                    confidence = 0.0
                    if self.run_entity_linking and self.wikidata_index:
                        wikidata_id = self.wikidata_index.get(surface.lower())
                        confidence = 1.0 if wikidata_id else 0.0
                    mentions.append(
                        EntityMention(
                            surface_form=surface,
                            entity_type=ent.label_,
                            start_char=ent.start_char,
                            end_char=ent.end_char,
                            wikidata_id=wikidata_id,
                            confidence=confidence,
                        )
                    )
                    count += 1
                yield rec.model_copy(update={"entity_mentions": mentions})
                records_done += 1
                if records_done % log_every == 0:
                    logger.info(
                        "[enricher] NER progress: %d records enriched (%d entities extracted)…",
                        records_done, count,
                    )
            record_buffer.clear()
            texts.clear()

        FLUSH_EVERY = batch_size * 16   # flush every 1024 records (16 batches)
        for record in records:
            record_buffer.append(record)
            texts.append(f"{record.title}. {record.body[:500]}")
            if len(record_buffer) >= FLUSH_EVERY:
                yield from _flush()

        if record_buffer:
            yield from _flush()

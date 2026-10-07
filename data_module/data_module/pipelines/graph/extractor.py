"""
Graph triple extractor — derives knowledge graph triples from CanonicalQA records.

Produces triples for:
  - (Answer) --[ANSWERS]--> (Question)
  - (Answer) --[ACCEPTED_FOR]--> (Question)  [if is_accepted]
  - (Question) --[TAGGED_WITH]--> (Tag)
  - (Question) --[DUPLICATE_OF]--> (Question)
  - (Question) --[RELATED_TO]--> (Question)
  - (Question) --[MENTIONS]--> (Entity)       [after NER enrichment]
  - (Answer)   --[MENTIONS]--> (Entity)
"""
from __future__ import annotations

import uuid
from typing import Generator

from ...schema.canonical import CanonicalQA
from ...schema.graph import Entity, Triple
from ...schema.provenance import PredicateType, SourceName


def _tid(s: str, p: str, o: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"triple:{s}:{p}:{o}"))


class TripleExtractor:
    """Extracts Triple and Entity objects from a CanonicalQA record."""

    def extract(
        self, record: CanonicalQA
    ) -> tuple[list[Entity], list[Triple]]:
        entities: list[Entity] = []
        triples: list[Triple] = []
        source = record.source

        # Question entity node
        q_entity = Entity(
            entity_id=record.id,
            entity_type="question",
            label=record.title[:200],
            source=source,
            properties={
                "score": record.score,
                "tags": record.tags,
                "language": record.language,
                "source_url": record.source_url or "",
            },
        )
        entities.append(q_entity)

        # Tag entities + TAGGED_WITH triples
        for tag in record.tags:
            tag_id = f"tag:{source.value}:{tag}"
            tag_entity = Entity(
                entity_id=tag_id,
                entity_type="tag",
                label=tag,
                source=source,
            )
            entities.append(tag_entity)
            triples.append(
                Triple(
                    triple_id=_tid(record.id, "TAGGED_WITH", tag_id),
                    subject_id=record.id,
                    subject_type="question",
                    predicate=PredicateType.TAGGED_WITH,
                    object_id=tag_id,
                    object_type="tag",
                    source=source,
                )
            )

        # DUPLICATE_OF triples
        if record.duplicate_of:
            triples.append(
                Triple(
                    triple_id=_tid(record.id, "DUPLICATE_OF", record.duplicate_of),
                    subject_id=record.id,
                    subject_type="question",
                    predicate=PredicateType.DUPLICATE_OF,
                    object_id=record.duplicate_of,
                    object_type="question",
                    source=source,
                )
            )

        # RELATED_TO triples
        for rel_id in record.related_ids:
            triples.append(
                Triple(
                    triple_id=_tid(record.id, "RELATED_TO", rel_id),
                    subject_id=record.id,
                    subject_type="question",
                    predicate=PredicateType.RELATED_TO,
                    object_id=rel_id,
                    object_type="question",
                    source=source,
                    properties={"weight": 0.5},
                )
            )

        # Answer entities + ANSWERS / ACCEPTED_FOR triples
        for ans in record.answers:
            a_entity = Entity(
                entity_id=ans.answer_id,
                entity_type="answer",
                label=ans.body[:100],
                source=source,
                properties={"score": ans.score, "is_accepted": ans.is_accepted},
            )
            entities.append(a_entity)

            triples.append(
                Triple(
                    triple_id=_tid(ans.answer_id, "ANSWERS", record.id),
                    subject_id=ans.answer_id,
                    subject_type="answer",
                    predicate=PredicateType.ANSWERS,
                    object_id=record.id,
                    object_type="question",
                    source=source,
                    properties={"score": ans.score},
                )
            )
            if ans.is_accepted:
                triples.append(
                    Triple(
                        triple_id=_tid(ans.answer_id, "ACCEPTED_FOR", record.id),
                        subject_id=ans.answer_id,
                        subject_type="answer",
                        predicate=PredicateType.ACCEPTED_FOR,
                        object_id=record.id,
                        object_type="question",
                        source=source,
                    )
                )

        # Entity MENTIONS triples (from NER enrichment)
        for mention in record.entity_mentions:
            ent_id = mention.wikidata_id or f"mention:{mention.surface_form.lower().replace(' ', '_')}"
            ent_entity = Entity(
                entity_id=ent_id,
                entity_type="named_entity",
                label=mention.surface_form,
                wikidata_id=mention.wikidata_id,
                properties={"entity_type": mention.entity_type},
            )
            entities.append(ent_entity)
            triples.append(
                Triple(
                    triple_id=_tid(record.id, "MENTIONS", ent_id),
                    subject_id=record.id,
                    subject_type="question",
                    predicate=PredicateType.MENTIONS,
                    object_id=ent_id,
                    object_type="named_entity",
                    source=source,
                    properties={"confidence": mention.confidence},
                )
            )

        return entities, triples

    def extract_stream(
        self, records: Generator[CanonicalQA, None, None]
    ) -> Generator[tuple[list[Entity], list[Triple]], None, None]:
        for record in records:
            yield self.extract(record)

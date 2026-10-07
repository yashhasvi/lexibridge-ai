"""
Graph builder — batches triple extraction and writes to the graph store.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Generator

from ...schema.canonical import CanonicalQA
from ...schema.graph import Entity, Triple
from .extractor import TripleExtractor

if TYPE_CHECKING:
    from ...storage.graph_store import GraphStore

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Extracts triples from a CanonicalQA stream and bulk-upserts them into the graph store."""

    def __init__(
        self,
        store: "GraphStore",
        batch_size: int = 1000,
    ) -> None:
        self.store = store
        self.batch_size = batch_size
        self.extractor = TripleExtractor()

    def build(self, records: Generator[CanonicalQA, None, None]) -> None:
        entity_batch: list[Entity] = []
        triple_batch: list[Triple] = []
        total_entities = total_triples = 0

        for entities, triples in self.extractor.extract_stream(records):
            entity_batch.extend(entities)
            triple_batch.extend(triples)

            if len(triple_batch) >= self.batch_size:
                self.store.upsert_entities(entity_batch)
                self.store.upsert_triples(triple_batch)
                total_entities += len(entity_batch)
                total_triples += len(triple_batch)
                entity_batch = []
                triple_batch = []
                logger.info("Graph: upserted %d entities, %d triples so far", total_entities, total_triples)

        # Flush remainder
        if triple_batch:
            self.store.upsert_entities(entity_batch)
            self.store.upsert_triples(triple_batch)
            total_entities += len(entity_batch)
            total_triples += len(triple_batch)

        logger.info("Graph build complete: %d entities, %d triples", total_entities, total_triples)

"""
Graph schema — triples, entities, and relations for knowledge graph construction.

Triples are derived from CanonicalQA records by the graph extractor pipeline stage.
The graph forms the backbone for Graph RAG and entity linking.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .provenance import PredicateType, SourceName


class Entity(BaseModel):
    """
    A node in the knowledge graph.

    Entities can be: questions, answers, tags, Wikidata items, NER mentions, topics.
    The `wikidata_id` field links internal entities to the Wikidata backbone.
    """
    entity_id: str                              # canonical UUID or Wikidata Q-ID
    entity_type: str                            # "question" | "answer" | "tag" |
                                                # "wikidata_item" | "topic" | "user"
    label: str                                  # human-readable name
    description: Optional[str] = None
    wikidata_id: Optional[str] = None           # e.g. "Q42"
    source: Optional[SourceName] = None
    properties: dict[str, Any] = Field(default_factory=dict)


class Triple(BaseModel):
    """
    A directed edge in the knowledge graph: subject --[predicate]--> object.

    Examples:
        Answer A42 --[ANSWERS]--> Question Q7
        Question Q7 --[TAGGED_WITH]--> Tag "python"
        Question Q7 --[DUPLICATE_OF]--> Question Q3
        Answer A42 --[MENTIONS]--> Entity "wd:Q28865"  (Python programming language)
        Question Q7 --[SUPPORTS]--> Claim C1  (for agentic fact-checking)
    """
    triple_id: str
    subject_id: str
    subject_type: str                           # "question" | "answer" | "entity" | "tag"
    predicate: PredicateType
    object_id: str
    object_type: str
    # Edge properties (weight, confidence, source of the assertion, etc.)
    properties: dict[str, Any] = Field(default_factory=dict)
    source: Optional[SourceName] = None

    def as_tuple(self) -> tuple[str, str, str]:
        """Return (subject_id, predicate, object_id) for graph lib insertion."""
        return (self.subject_id, self.predicate.value, self.object_id)


class SubGraph(BaseModel):
    """
    A retrieved subgraph — returned by the graph RAG fetcher.
    Contains a seed entity/question + 1-hop or 2-hop neighbourhood.
    """
    seed_id: str
    entities: list[Entity] = Field(default_factory=list)
    triples: list[Triple] = Field(default_factory=list)
    depth: int = 1

    def to_context_str(self) -> str:
        """Render the subgraph as a natural-language context string for LLM prompts."""
        lines = [f"[Knowledge Graph — seed: {self.seed_id}]"]
        for t in self.triples:
            lines.append(f"  {t.subject_id} --[{t.predicate.value}]--> {t.object_id}")
        return "\n".join(lines)

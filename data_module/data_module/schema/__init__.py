"""data_module.schema — Pydantic models for all data records."""
from .canonical import CanonicalAnswer, CanonicalQA, EntityMention
from .chunk import ChunkMetadata, ChunkRecord
from .graph import Entity, SubGraph, Triple
from .provenance import ChunkType, License, PredicateType, SourceName

__all__ = [
    "CanonicalAnswer",
    "CanonicalQA",
    "EntityMention",
    "ChunkMetadata",
    "ChunkRecord",
    "Entity",
    "SubGraph",
    "Triple",
    "ChunkType",
    "License",
    "PredicateType",
    "SourceName",
]

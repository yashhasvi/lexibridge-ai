"""
Provenance and license enums used across all schema models.
"""
from __future__ import annotations

from enum import Enum


class License(str, Enum):
    CC_BY_SA_25 = "cc-by-sa-2.5"
    CC_BY_SA_30 = "cc-by-sa-3.0"
    CC_BY_SA_40 = "cc-by-sa-4.0"
    CC_BY_40 = "cc-by-4.0"
    CC0 = "cc0"
    APACHE_20 = "apache-2.0"
    MIT = "mit"
    GFDL = "gfdl-1.3"
    UNKNOWN = "unknown"


class SourceName(str, Enum):
    STACKEXCHANGE = "stackexchange"
    WIKIPEDIA = "wikipedia"
    WIKIDATA = "wikidata"
    SQUAD = "squad"
    NATURAL_QUESTIONS = "natural_questions"
    MS_MARCO = "ms_marco"
    HOTPOTQA = "hotpotqa"
    TRIVIAQA = "triviaqa"
    OPENASSISTANT = "openassistant"
    # User-supplied CSV / JSON under data/raw/local_file/
    LOCAL_FILE = "local_file"


class ChunkType(str, Enum):
    """How a chunk was derived from its parent CanonicalQA."""
    CANONICAL_QA = "canonical_qa"        # question + best/accepted answer combined
    QUESTION_ONLY = "question_only"      # title + body only
    ANSWER_ONLY = "answer_only"          # a single answer
    MULTI_HOP = "multi_hop"              # question + multiple supporting passages
    CONVERSATION = "conversation"        # full multi-turn thread
    PASSAGE = "passage"                  # plain passage (Wikipedia, evidence doc)


class PredicateType(str, Enum):
    """Knowledge graph edge labels."""
    ANSWERS = "ANSWERS"
    ACCEPTED_FOR = "ACCEPTED_FOR"
    TAGGED_WITH = "TAGGED_WITH"
    DUPLICATE_OF = "DUPLICATE_OF"
    RELATED_TO = "RELATED_TO"
    MENTIONS = "MENTIONS"
    SUPPORTS = "SUPPORTS"
    SUBTOPIC_OF = "SUBTOPIC_OF"
    AUTHORED_BY = "AUTHORED_BY"
    INSTANCE_OF = "INSTANCE_OF"
    SUBCLASS_OF = "SUBCLASS_OF"
    SAME_AS = "SAME_AS"

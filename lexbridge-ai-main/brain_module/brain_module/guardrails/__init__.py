"""
Guardrails — multi-layer validation for the RAG synthesis pipeline.

Modules:
  retrieval_filter    Pre-synthesis chunk filtering (min score, source diversity)
  response_validator  Post-generation heuristic checks (contradiction, alignment)
  llm_judge           Optional LLM-as-judge second-pass validation
"""
from .retrieval_filter import filter_low_relevance, filter_score_gap, cap_source_diversity
from .response_validator import validate_response, ValidationResult

__all__ = [
    "filter_low_relevance",
    "filter_score_gap",
    "cap_source_diversity",
    "validate_response",
    "ValidationResult",
]

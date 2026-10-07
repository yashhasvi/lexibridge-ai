# File: __init__.py

## Purpose
Guardrails for the RAG synthesis pipeline, providing multi-layer validation.

## Key Components
* `retrieval_filter`: Pre-synthesis filtering of chunks based on relevance and source diversity.
* `response_validator`: Post-generation heuristic checks for contradictions and alignment.
* Optional LLM-as-judge second-pass validation using `llm_judge`.

## Important Logic
The file exports several key functions for validation:
* `filter_low_relevance`
* `filter_score_gap`
* `cap_source_diversity`
* `validate_response`
* `ValidationResult`

## Dependencies
None explicitly mentioned, but likely relies on other modules in the same package.

## Notes
This module provides a framework for validating outputs from the RAG synthesis pipeline.
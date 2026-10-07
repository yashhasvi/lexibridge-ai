# File: intent_classifier.py

## Purpose
Classifies user queries into one of four intent categories using a two-layer approach:
  1. Rule-based fast path (regex + keyword heuristics) — zero latency
  2. Embedding similarity fallback using intfloat/e5-small-v2

## Key Components
* `IntentClassifier` class with `classify` method
* Two sets of rules: `FACTUAL_PATTERNS`, `_MULTI_HOP_PATTERNS`, `_TECHNICAL_PATTERNS`, `_UNANSWERABLE_PATTERNS`, and `_CHITCHAT_PATTERNS`
* Embedding model (intfloat/e5-small-v2) used for fallback classification
* Label embeddings computed from a set of exemplar queries

## Important Logic
* `IntentClassifier` class uses a two-layer approach: rule-based fast path followed by embedding similarity fallback if rules don't match
* `_rule_classify` function applies the rule-based patterns to classify queries
* `_embedding_classify` function uses the embedding model and label embeddings to classify queries

## Dependencies
* sentence_transformers library for embedding model
* numpy library for numerical computations
* typing library for type hints

## Notes
* The code includes caching mechanisms using `lru_cache` decorator to improve performance
* The embedding model used is intfloat/e5-small-v2, which requires a query: prefix for queries and passage: prefix for passages when encoding
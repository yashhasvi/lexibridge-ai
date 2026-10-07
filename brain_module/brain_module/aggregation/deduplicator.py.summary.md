# File: deduplicator.py

## Purpose
Removes near-duplicate chunks from an aggregated pool using two-stage deduplication.

## Key Components
- `exact_dedup`: removes exact duplicates based on normalized text hashes.
- `semantic_dedup`: removes semantically similar chunks via cosine similarity on sentence embeddings.

## Important Logic
Two-stage deduplication process:
1. Exact hash dedup (SHA256 of normalised text)
2. Semantic dedup via cosine similarity on sentence embeddings (if exact dedup doesn't reduce pool enough)

## Dependencies
- `hashlib` for SHA256 hashing
- `logging` for logging warnings
- `numpy` for numerical computations
- `sentence-transformers` library for sentence embeddings

## Notes
The code uses a caching mechanism to load the embedding model, and it logs warnings if the model cannot be loaded. The semantic deduplication process requires the `sentence-transformers` library to be installed.
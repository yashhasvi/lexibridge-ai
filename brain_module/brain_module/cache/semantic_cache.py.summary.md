# File: semantic_cache.py

## Purpose
Embedding-similarity cache for near-duplicate queries, allowing paraphrased queries to hit the cache even if the text differs.

## Key Components
- Stores (query_embedding, response_json) pairs in an in-process list.
- Uses cosine similarity to match queries with stored query embeddings.
- Has a maximum size and evicts oldest entries on overflow.

## Important Logic
- `get()`: encodes the query, does a brute-force cosine scan of stored embeddings, and returns the best match if similarity >= threshold.
- `set()`: adds a new entry to the cache, serialising response dictionaries as JSON.

## Dependencies
- `numpy` for numerical computations.
- `json` for serialising response dictionaries.

## Notes
- Intentionally in-process (no Redis) due to small embedding vectors and fast brute-force scan times.
- Environment variables control cache behaviour: `SEMANTIC_CACHE_ENABLED`, `SEMANTIC_CACHE_THRESHOLD`, and `SEMANTIC_CACHE_MAXSIZE`.
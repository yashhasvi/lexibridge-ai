# File: embedding_cache.py

## Purpose
LRU cache for query embedding vectors to avoid re-encoding the same query text on every request.

## Key Components
* `EmbeddingCache` class that wraps an embedder's `encode` method
* Normalized query text is used as cache key
* Cache operates on individual strings, handling mixed hits/misses within a batch

## Important Logic
* `encode` method checks cache for available vectors and returns them if found
* If not found, the method calls the embedder's `encode` method to compute new vectors
* New vectors are then added to the cache

## Dependencies
* sentence-transformers or OpenAI embedders
* numpy library

## Notes
* Cache is enabled by default with a maximum size of 2048 entries
* Environment variables can be used to enable/disable caching and set maximum cache size
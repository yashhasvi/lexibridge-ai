# File: query_cache.py

## Purpose
Cache layer for brain_module responses that uses Redis as the primary backend and falls back to an in-process LRU cache if Redis is unavailable.

## Key Components
- `_cache_key`: generates a unique key from a query string using SHA256 hashing.
- `QueryCache` class: async interface for caching, with methods for getting, setting, deleting, and clearing cached values.
- `_LRUStore` class: in-process LRU cache implementation using an ordered dictionary.

## Important Logic
- The cache layer uses Redis as the primary backend, but falls back to the in-process LRU cache if Redis is unavailable or not configured.
- Cached values are JSON-serialised BrainResponse dicts.
- TTL defaults to 24 hours (configurable).

## Dependencies
- `redis.asyncio` library for interacting with Redis.
- `functools.lru_cache` for implementing the in-process LRU cache.

## Notes
- The `QueryCache.from_env()` method allows instantiation of the cache layer using environment variables.
- The cache layer uses a thread-safe ordered dictionary for storing cached values.
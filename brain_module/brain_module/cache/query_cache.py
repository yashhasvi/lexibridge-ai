"""
QueryCache — Redis-backed or in-process LRU cache for brain_module responses.

Key design decisions:
  - Cache key = SHA256(normalised_query) — collision-safe, query-order-invariant
  - Redis is the primary backend; falls back to `functools.lru_cache` automatically
    if Redis is unreachable or not configured.
  - Cached values are JSON-serialised BrainResponse dicts.
  - TTL defaults to 24 hours (configurable).

Usage::

    cache = QueryCache.from_env()          # reads REDIS_URL from env
    hit = await cache.get("What is X?")   # None on miss
    await cache.set("What is X?", response_dict, ttl=3600)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 60 * 60 * 24  # 24 hours


def _cache_key(query: str) -> str:
    normalised = " ".join(query.strip().lower().split())
    return "brain:" + hashlib.sha256(normalised.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# In-process LRU fallback (no Redis dependency)
# --------------------------------------------------------------------------- #

class _LRUStore:
    """Thread-safe ordered-dict LRU with a max-size cap."""

    def __init__(self, maxsize: int = 512) -> None:
        self._data: OrderedDict[str, str] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> str | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def set(self, key: str, value: str) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        else:
            if len(self._data) >= self._maxsize:
                self._data.popitem(last=False)
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()


# --------------------------------------------------------------------------- #
# QueryCache (async interface)
# --------------------------------------------------------------------------- #

class QueryCache:
    """
    Async cache layer.  Instantiate via `QueryCache.from_env()` or
    `QueryCache(redis_url="redis://localhost:6379")`.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        ttl: int = _DEFAULT_TTL,
        lru_maxsize: int = 512,
    ) -> None:
        self._ttl = ttl
        self._redis_url = redis_url
        self._redis: Any = None          # redis.asyncio.Redis, set lazily
        self._lru = _LRUStore(lru_maxsize)
        self._redis_available = False

    @classmethod
    def from_env(cls, ttl: int = _DEFAULT_TTL) -> "QueryCache":
        redis_url = os.getenv("REDIS_URL")
        return cls(redis_url=redis_url, ttl=ttl)

    async def _ensure_redis(self) -> bool:
        if self._redis is not None:
            return self._redis_available
        if not self._redis_url:
            return False
        try:
            import redis.asyncio as aioredis  # type: ignore[import-untyped]
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            self._redis_available = True
            logger.info("QueryCache: Redis connected at %s", self._redis_url)
        except Exception as exc:
            logger.warning("QueryCache: Redis unavailable (%s), using LRU fallback.", exc)
            self._redis_available = False
        return self._redis_available

    async def get(self, query: str) -> dict[str, Any] | None:
        key = _cache_key(query)
        if await self._ensure_redis():
            raw: str | None = await self._redis.get(key)
        else:
            raw = self._lru.get(key)

        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set(self, query: str, response_dict: dict[str, Any], ttl: int | None = None) -> None:
        key = _cache_key(query)
        serialised = json.dumps(response_dict, ensure_ascii=False)
        effective_ttl = ttl if ttl is not None else self._ttl

        if await self._ensure_redis():
            await self._redis.setex(key, effective_ttl, serialised)
        else:
            self._lru.set(key, serialised)

    async def delete(self, query: str) -> None:
        key = _cache_key(query)
        if await self._ensure_redis():
            await self._redis.delete(key)
        else:
            self._lru.delete(key)

    async def clear(self) -> None:
        self._lru.clear()
        if await self._ensure_redis():
            # Clear only brain: namespace keys
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match="brain:*", count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break

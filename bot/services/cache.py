from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Protocol

from core.config import RedisConfig

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover - optional dependency at runtime
    redis = None


class CacheBackend(Protocol):
    async def get(self, key: str) -> Any: ...
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def incr(self, key: str, ttl: int | None = None) -> int: ...
    async def close(self) -> None: ...


@dataclass(slots=True)
class _MemoryValue:
    value: Any
    expires_at: float | None


class MemoryCache(CacheBackend):
    def __init__(self) -> None:
        self._store: dict[str, _MemoryValue] = {}
        self._lock = asyncio.Lock()

    def _is_expired(self, entry: _MemoryValue) -> bool:
        if entry.expires_at is None:
            return False
        return time.time() >= entry.expires_at

    async def get(self, key: str) -> Any:
        async with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            if self._is_expired(entry):
                self._store.pop(key, None)
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        async with self._lock:
            expires_at = time.time() + ttl if ttl else None
            self._store[key] = _MemoryValue(value=value, expires_at=expires_at)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def incr(self, key: str, ttl: int | None = None) -> int:
        async with self._lock:
            entry = self._store.get(key)
            now = time.time()
            if not entry or self._is_expired(entry):
                expires_at = now + ttl if ttl else None
                self._store[key] = _MemoryValue(value=1, expires_at=expires_at)
                return 1
            new_val = int(entry.value) + 1
            self._store[key] = _MemoryValue(value=new_val, expires_at=entry.expires_at)
            return new_val

    async def close(self) -> None:
        self._store.clear()


class RedisCache(CacheBackend):
    def __init__(self, url: str) -> None:
        if redis is None:
            raise RuntimeError("Redis dependency not installed. Add redis package.")
        self._client = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Any:
        return await self._client.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if ttl:
            await self._client.set(key, value, ex=ttl)
        else:
            await self._client.set(key, value)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def incr(self, key: str, ttl: int | None = None) -> int:
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            if ttl:
                pipe.expire(key, ttl)
            result = await pipe.execute()
        return int(result[0])

    async def close(self) -> None:
        await self._client.close()


async def build_cache(config: RedisConfig) -> CacheBackend:
    if config.enabled:
        return RedisCache(config.url)
    return MemoryCache()

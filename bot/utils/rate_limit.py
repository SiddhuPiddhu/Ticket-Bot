from __future__ import annotations

from dataclasses import dataclass

from services.cache import CacheBackend


@dataclass(slots=True)
class RateLimitResult:
    allowed: bool
    current: int
    limit: int


class DistributedRateLimiter:
    def __init__(self, cache: CacheBackend) -> None:
        self.cache = cache

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        current = await self.cache.incr(key, ttl=window_seconds)
        return RateLimitResult(
            allowed=current <= limit,
            current=current,
            limit=limit,
        )

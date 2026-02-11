from __future__ import annotations

import asyncio

import pytest

from services.cache import MemoryCache
from utils.rate_limit import DistributedRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_blocks_after_limit() -> None:
    cache = MemoryCache()
    limiter = DistributedRateLimiter(cache)

    result1 = await limiter.hit("k1", limit=2, window_seconds=1)
    result2 = await limiter.hit("k1", limit=2, window_seconds=1)
    result3 = await limiter.hit("k1", limit=2, window_seconds=1)

    assert result1.allowed is True
    assert result2.allowed is True
    assert result3.allowed is False


@pytest.mark.asyncio
async def test_rate_limiter_resets_after_window() -> None:
    cache = MemoryCache()
    limiter = DistributedRateLimiter(cache)

    result1 = await limiter.hit("k2", limit=1, window_seconds=1)
    assert result1.allowed is True

    await asyncio.sleep(1.1)
    result2 = await limiter.hit("k2", limit=1, window_seconds=1)
    assert result2.allowed is True

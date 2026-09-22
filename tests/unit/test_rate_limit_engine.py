"""T010 — Unit tests for rate_limit counting engine (AD-3, AD-4, AD-5).

Tests:
1. _InMemoryWindow respects limit, returns correct retry_after, resets after window.
2. Redis pipeline check works with active Redis client.
3. Redis failure / timeout trips circuit breaker and falls back to _InMemoryWindow.
4. While breaker is tripped, subsequent calls directly hit in-memory fallback without touching Redis.
5. reset_for_tests() resets circuit breaker and in-memory dict.
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
import redis.exceptions as redis_exceptions

from app.core import rate_limit
from app.core.rate_limit import (
    RateLimitVerdict,
    _InMemoryWindow,
    check,
    reset_for_tests,
)


def test_in_memory_window_counting():
    window = _InMemoryWindow(max_entries=10)
    key = "test_key"
    limit = 2
    win_sec = 60

    # 1st call
    v1 = window.check(key, limit, win_sec)
    assert v1.allowed is True
    assert v1.retry_after > 0

    # 2nd call
    v2 = window.check(key, limit, win_sec)
    assert v2.allowed is True

    # 3rd call (exceeded)
    v3 = window.check(key, limit, win_sec)
    assert v3.allowed is False
    assert v3.retry_after > 0


def test_in_memory_window_expiry(monkeypatch):
    window = _InMemoryWindow()
    current_time = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: current_time)

    # Fill to limit
    v1 = window.check("k", 1, 10)
    assert v1.allowed is True
    v2 = window.check("k", 1, 10)
    assert v2.allowed is False

    # Advance time beyond window
    current_time = 1011.0
    v3 = window.check("k", 1, 10)
    assert v3.allowed is True


@pytest.mark.asyncio
async def test_redis_check_success(redis_client):
    reset_for_tests()
    key = "rl:unit:test"
    v1 = await check(key, limit=2, window_seconds=60)
    assert v1.allowed is True
    assert v1.retry_after == 60 or v1.retry_after == 59

    v2 = await check(key, limit=2, window_seconds=60)
    assert v2.allowed is True

    v3 = await check(key, limit=2, window_seconds=60)
    assert v3.allowed is False
    assert v3.retry_after > 0


@pytest.mark.asyncio
async def test_redis_failure_trips_circuit_breaker():
    reset_for_tests()
    with patch("app.core.rate_limit.redis_client.pipeline") as mock_pipeline:
        mock_pipe = AsyncMock()
        mock_pipe.execute.side_effect = redis_exceptions.ConnectionError("Redis down")
        mock_pipeline.return_value = mock_pipe

        # Check trips breaker and uses fallback
        v = await check("down_key", limit=1, window_seconds=60)
        assert v.allowed is True

        # Next check within breaker cooldown should NOT even call redis pipeline
        mock_pipeline.reset_mock()
        v2 = await check("down_key", limit=1, window_seconds=60)
        assert v2.allowed is False  # exceeded limit 1 in fallback
        mock_pipeline.assert_not_called()

    reset_for_tests()

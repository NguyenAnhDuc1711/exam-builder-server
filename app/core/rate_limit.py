import asyncio
import logging
import time
from typing import NamedTuple

import redis.exceptions as redis_exceptions

from app.core.config import settings
from app.core.redis import redis_client

logger = logging.getLogger(__name__)

_MAX_FALLBACK_ENTRIES = 10000


class RateLimitVerdict(NamedTuple):
    allowed: bool
    retry_after: int


class _InMemoryWindow:
    """In-process fallback counter with lazy expiry and a capacity ceiling."""

    def __init__(self, max_entries: int = _MAX_FALLBACK_ENTRIES) -> None:
        self._store: dict[str, tuple[int, float]] = {}
        self._max_entries = max_entries

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitVerdict:
        now = time.monotonic()
        count, expires_at = self._store.get(key, (0, 0.0))

        if now >= expires_at:
            count = 0
            expires_at = now + window_seconds

        count += 1

        # Prune if over capacity
        if len(self._store) >= self._max_entries and key not in self._store:
            self._prune(now)
            if len(self._store) >= self._max_entries:
                # Still full, drop an arbitrary key
                self._store.pop(next(iter(self._store)), None)

        self._store[key] = (count, expires_at)
        allowed = count <= limit
        retry_after = max(int(expires_at - now), 1)
        return RateLimitVerdict(allowed=allowed, retry_after=retry_after)

    def _prune(self, now: float) -> None:
        expired = [k for k, (_, exp) in self._store.items() if now >= exp]
        for k in expired:
            self._store.pop(k, None)

    def clear(self) -> None:
        self._store.clear()


_fallback = _InMemoryWindow()
_redis_unavailable_until: float = 0.0


async def check(key: str, limit: int, window_seconds: int) -> RateLimitVerdict:
    """Check and increment counter for the given key.

    Uses Redis pipeline when available; trips circuit breaker on error/timeout (>50ms)
    and falls back to in-memory window.
    """
    global _redis_unavailable_until
    now = time.monotonic()

    # Circuit breaker check (AD-4)
    if now < _redis_unavailable_until:
        return _fallback.check(key, limit, window_seconds)

    try:
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        pipe.ttl(key)

        timeout = settings.RATE_LIMIT_REDIS_TIMEOUT_MS / 1000.0
        results = await asyncio.wait_for(pipe.execute(), timeout=timeout)
        count, _, ttl = results

        allowed = count <= limit
        retry_after = max(int(ttl), 1)
        return RateLimitVerdict(allowed=allowed, retry_after=retry_after)

    except (
        redis_exceptions.RedisError,
        TimeoutError,
        OSError,
        asyncio.TimeoutError,
    ) as exc:
        _redis_unavailable_until = (
            time.monotonic() + settings.RATE_LIMIT_BREAKER_COOLDOWN_SECONDS
        )
        logger.warning(
            "redis_rate_limit_unavailable",
            extra={
                "error": str(exc),
                "cooldown_seconds": settings.RATE_LIMIT_BREAKER_COOLDOWN_SECONDS,
            },
        )
        return _fallback.check(key, limit, window_seconds)


def reset_for_tests() -> None:
    """Reset in-memory fallback state and circuit breaker for test isolation."""
    global _redis_unavailable_until
    _redis_unavailable_until = 0.0
    _fallback.clear()

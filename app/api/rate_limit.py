"""FastAPI rate limiting dependencies (AD-2, AD-6, AD-7, T011).

Provides:
- `rate_limit(group)`: dependency for authenticated endpoints keyed by user_id.
- `login_rate_limit`: dedicated dependency for POST /auth/login checking IP and email independently.
- `refresh_rate_limit`: dependency for POST /auth/refresh checking IP.
- `ip_rate_limit(group)`: dependency for unauthenticated endpoints.
- Rejection helper `_reject`: logs NTH-1 warning and raises HTTP 429 with Retry-After header.
- Tagged with `__rate_limit_group__` on callables for coverage verification (T012).
"""

import logging
from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.rate_limit import check
from app.core.security import hash_token
from app.models.user import User
from app.schemas.auth import LoginRequest

logger = logging.getLogger(__name__)


def _get_group_config(group: str) -> tuple[int, int]:
    """Dynamically resolve (limit, window_seconds) from settings."""
    if group == "auth":
        return settings.RATE_LIMIT_AUTH_MAX, settings.RATE_LIMIT_AUTH_WINDOW_SECONDS
    elif group == "write":
        return settings.RATE_LIMIT_WRITE_MAX, settings.RATE_LIMIT_WRITE_WINDOW_SECONDS
    elif group == "submit":
        return settings.RATE_LIMIT_SUBMIT_MAX, settings.RATE_LIMIT_SUBMIT_WINDOW_SECONDS
    elif group == "read":
        return settings.RATE_LIMIT_READ_MAX, settings.RATE_LIMIT_READ_WINDOW_SECONDS
    raise ValueError(f"Unknown rate limit group: {group}")


def _reject(group: str, kind: str, identifier: str, retry_after: int) -> None:
    """Log NTH-1 rate limit rejection and raise 429 with Retry-After header."""
    logger.warning(
        "rate_limit_exceeded",
        extra={
            "group": group,
            "kind": kind,
            "identifier": identifier,
            "retry_after": retry_after,
        },
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests. Please try again later.",
        headers={"Retry-After": str(retry_after)},
    )


def rate_limit(group: str) -> Callable[..., Any]:
    """Dependency factory for authenticated routes keyed by authenticated user_id (FR-2, AD-2)."""

    async def _rate_limit_dependency(
        current_user: User = Depends(get_current_user),
    ) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        limit, window = _get_group_config(group)
        key = f"rl:{group}:u:{current_user.id}"
        verdict = await check(key, limit, window)

        if not verdict.allowed:
            _reject(group, "u", str(current_user.id), verdict.retry_after)

    _rate_limit_dependency.__rate_limit_group__ = group
    return _rate_limit_dependency


async def login_rate_limit(
    request: Request,
    body: LoginRequest,
) -> None:
    """Login rate limiter checking IP and email keys independently (FR-3, AD-7).

    Increments both counters before deciding, preventing an attacker from keeping
    one counter cold by tripping the other.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return

    limit, window = _get_group_config("auth")
    ip = request.client.host if request.client else "unknown"
    normalized_email = body.email.strip().lower()
    email_hash = hash_token(normalized_email)

    ip_key = f"rl:auth:ip:{ip}"
    em_key = f"rl:auth:em:{email_hash}"

    # Increment both before either verdict (AD-7)
    v_ip = await check(ip_key, limit, window)
    v_em = await check(em_key, limit, window)

    if not v_ip.allowed:
        _reject("auth", "ip", ip, v_ip.retry_after)
    if not v_em.allowed:
        _reject("auth", "em", email_hash, v_em.retry_after)


login_rate_limit.__rate_limit_group__ = "auth"


async def refresh_rate_limit(request: Request) -> None:
    """Refresh rate limiter checking IP key under auth group (FR-3)."""
    if not settings.RATE_LIMIT_ENABLED:
        return

    limit, window = _get_group_config("auth")
    ip = request.client.host if request.client else "unknown"
    ip_key = f"rl:auth:ip:{ip}"

    v_ip = await check(ip_key, limit, window)
    if not v_ip.allowed:
        _reject("auth", "ip", ip, v_ip.retry_after)


refresh_rate_limit.__rate_limit_group__ = "auth"


def ip_rate_limit(group: str = "auth") -> Callable[..., Any]:
    """Dependency factory for unauthenticated endpoints checking client IP."""

    async def _ip_dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        limit, window = _get_group_config(group)
        ip = request.client.host if request.client else "unknown"
        ip_key = f"rl:{group}:ip:{ip}"

        v_ip = await check(ip_key, limit, window)
        if not v_ip.allowed:
            _reject(group, "ip", ip, v_ip.retry_after)

    _ip_dependency.__rate_limit_group__ = group
    return _ip_dependency

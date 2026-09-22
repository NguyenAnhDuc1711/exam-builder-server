"""T011 — Unit tests for rate_limit dependencies (AD-2, AD-6, AD-7, FR-6, NTH-1).

Tests:
1. rate_limit(group) raises HTTPException(429) with Retry-After header when limit exceeded.
2. NTH-1 log record emitted on 429.
3. RATE_LIMIT_ENABLED=False short-circuits.
4. login_rate_limit checks both IP and email counters.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.rate_limit import (
    login_rate_limit,
    rate_limit,
    refresh_rate_limit,
)
from app.core.config import settings
from app.core.rate_limit import RateLimitVerdict
from app.models.user import User
from app.schemas.auth import LoginRequest


@pytest.mark.asyncio
async def test_rate_limit_dependency_exceeded_raises_429(caplog):
    dep = rate_limit("write")
    user = User(id=10, email="u@example.com", role="user")

    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch(
            "app.api.rate_limit.check",
            AsyncMock(return_value=RateLimitVerdict(allowed=False, retry_after=45)),
        ):
            with caplog.at_level(logging.WARNING, logger="app.api.rate_limit"):
                with pytest.raises(HTTPException) as exc_info:
                    await dep(current_user=user)

                assert exc_info.value.status_code == 429
                assert exc_info.value.headers["Retry-After"] == "45"
                assert "Too many requests" in exc_info.value.detail

            # NTH-1 logging check
            assert any(
                r.levelname == "WARNING"
                and r.message == "rate_limit_exceeded"
                and r.group == "write"
                and r.kind == "u"
                and r.identifier == "10"
                and r.retry_after == 45
                for r in caplog.records
            )


@pytest.mark.asyncio
async def test_rate_limit_disabled_short_circuits():
    dep = rate_limit("write")
    user = User(id=10, email="u@example.com", role="user")

    with patch.object(settings, "RATE_LIMIT_ENABLED", False):
        with patch("app.api.rate_limit.check") as mock_check:
            await dep(current_user=user)
            mock_check.assert_not_called()


@pytest.mark.asyncio
async def test_login_rate_limit_checks_composite_key():
    request = MagicMock()
    request.client.host = "1.2.3.4"
    body = LoginRequest(email="Victim@example.com", password="pw")

    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch(
            "app.api.rate_limit.check",
            AsyncMock(return_value=RateLimitVerdict(allowed=True, retry_after=60)),
        ) as mock_check:
            await login_rate_limit(request=request, body=body)

            assert mock_check.call_count == 1
            called_key = mock_check.call_args[0][0]
            assert called_key.startswith("rl:auth:login:1.2.3.4:")

"""T090 — SC-2: Fallback to in-memory counter when Redis is unreachable.

Asserts:
- When Redis raises ConnectionError or times out, requests are still served (0 x 5xx).
- Circuit breaker opens for 5s, sending subsequent requests straight to _InMemoryWindow.
- Rate limits are still enforced by in-memory counter (returns 429 on request N+1).
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import redis.exceptions as redis_exceptions
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_session
from app.core import rate_limit as rate_limit_module
from app.core.rate_limit import reset_for_tests
from app.core.redis import redis_client
from app.core.security import hash_password
from app.main import app
from app.models.question import Option, Question
from app.models.user import User


@pytest_asyncio.fixture(autouse=True)
async def clean_rate_limit(redis_client):
    reset_for_tests()
    await redis_client.flushdb()
    yield
    reset_for_tests()
    await redis_client.flushdb()
    from app.core.redis import redis_client as app_redis
    await app_redis.connection_pool.disconnect()


@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_token(session, client):
    admin = User(
        email="admin_fallback@example.com",
        password_hash=hash_password("adminpw123"),
        role="admin",
    )
    session.add(admin)
    await session.commit()

    res = await client.post(
        "/auth/login",
        json={"email": "admin_fallback@example.com", "password": "adminpw123"},
    )
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_sc2_redis_connection_error_falls_back_and_enforces_limit(client, admin_token):
    """Redis raises ConnectionError: breaker opens, in-memory counter enforces limits (429 on N+1)."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "text": "Fallback question",
        "options": json.dumps([{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]),
    }

    mock_pipe = AsyncMock()
    mock_pipe.execute.side_effect = redis_exceptions.ConnectionError("Redis connection refused")

    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch.object(settings, "RATE_LIMIT_WRITE_MAX", 2):
            with patch.object(settings, "RATE_LIMIT_WRITE_WINDOW_SECONDS", 60):
                reset_for_tests()

                with patch.object(redis_client, "pipeline", return_value=mock_pipe):
                    # Request 1: Redis error occurs -> breaker trips -> in-memory allowed (201)
                    r1 = await client.post("/questions", data=payload, headers=headers)
                    assert r1.status_code == 201

                    # Breaker should now be open
                    assert rate_limit_module._redis_unavailable_until > 0.0

                    # Request 2: Breaker open -> straight to in-memory -> allowed (201)
                    r2 = await client.post("/questions", data=payload, headers=headers)
                    assert r2.status_code == 201

                    # Request 3: Over limit -> in-memory rejects with 429
                    r3 = await client.post("/questions", data=payload, headers=headers)
                    assert r3.status_code == 429
                    assert int(r3.headers["Retry-After"]) >= 1
                    assert r3.json()["detail"] == "Too many requests. Please try again later."


@pytest.mark.asyncio
async def test_sc2_redis_timeout_falls_back_safely(client, admin_token):
    """Redis times out (> 50ms): breaker opens, requests served gracefully via fallback."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "text": "Timeout fallback question",
        "options": json.dumps([{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]),
    }

    async def _slow_execute():
        await asyncio.sleep(0.2)
        return [1, 1, 60]

    mock_pipe = AsyncMock()
    mock_pipe.execute.side_effect = _slow_execute

    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch.object(settings, "RATE_LIMIT_WRITE_MAX", 2):
            with patch.object(settings, "RATE_LIMIT_REDIS_TIMEOUT_MS", 20):
                reset_for_tests()

                with patch.object(redis_client, "pipeline", return_value=mock_pipe):
                    # Request 1: Times out -> caught -> breaker trips -> fallback allows (201)
                    r1 = await client.post("/questions", data=payload, headers=headers)
                    assert r1.status_code == 201
                    assert rate_limit_module._redis_unavailable_until > 0.0

                    # Request 2: Breaker open -> in-memory allowed (201)
                    r2 = await client.post("/questions", data=payload, headers=headers)
                    assert r2.status_code == 201

                    # Request 3: In-memory returns 429
                    r3 = await client.post("/questions", data=payload, headers=headers)
                    assert r3.status_code == 429

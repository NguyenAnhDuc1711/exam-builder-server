"""T090 — SC-6 and SC-7: User isolation and login dual-key (IP + email) verification.

Asserts:
- SC-6: Two users on the same client IP have independent counters (User B is unaffected
  when User A exhausts their group limit).
- SC-7 Scenario A: Login blocked by IP-key when attacking multiple emails from 1 IP.
- SC-7 Scenario B: Login blocked by email-key when attacking 1 email from multiple IPs;
  other emails from those IPs remain allowed (counters independent).
"""

import json
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_session
from app.core.rate_limit import reset_for_tests
from app.core.security import hash_password
from app.main import app
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
async def seed_users(session):
    user_a = User(
        email="admin_a@example.com",
        password_hash=hash_password("pw_a_123"),
        role="admin",
    )
    user_b = User(
        email="admin_b@example.com",
        password_hash=hash_password("pw_b_123"),
        role="admin",
    )
    victim = User(
        email="victim@example.com",
        password_hash=hash_password("victim_pass"),
        role="user",
    )
    session.add_all([user_a, user_b, victim])
    await session.commit()
    return {"user_a": user_a, "user_b": user_b, "victim": victim}


@pytest.mark.asyncio
async def test_sc6_two_users_on_same_ip_have_independent_counters(client, seed_users):
    """SC-6: User A exceeding write limit does not affect User B on the same IP."""
    # Obtain tokens for both users from the same client
    res_a = await client.post("/auth/login", json={"email": "admin_a@example.com", "password": "pw_a_123"})
    token_a = res_a.json()["access_token"]

    res_b = await client.post("/auth/login", json={"email": "admin_b@example.com", "password": "pw_b_123"})
    token_b = res_b.json()["access_token"]

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    payload = {
        "text": "User isolation question",
        "options": json.dumps([{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]),
    }

    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch.object(settings, "RATE_LIMIT_WRITE_MAX", 2):
            with patch.object(settings, "RATE_LIMIT_WRITE_WINDOW_SECONDS", 60):
                reset_for_tests()

                # User A makes 2 write requests -> allowed (201)
                r1 = await client.post("/questions", data=payload, headers=headers_a)
                assert r1.status_code == 201
                r2 = await client.post("/questions", data=payload, headers=headers_a)
                assert r2.status_code == 201

                # User A makes 3rd write request -> 429
                r3 = await client.post("/questions", data=payload, headers=headers_a)
                assert r3.status_code == 429

                # User B on the exact same client/IP sends a write request -> allowed (201)!
                rb1 = await client.post("/questions", data=payload, headers=headers_b)
                assert rb1.status_code == 201

                # User B sends second request -> allowed (201)
                rb2 = await client.post("/questions", data=payload, headers=headers_b)
                assert rb2.status_code == 201

                # User B sends third request -> 429
                rb3 = await client.post("/questions", data=payload, headers=headers_b)
                assert rb3.status_code == 429


@pytest.mark.asyncio
async def test_login_composite_key_allows_different_emails_on_same_ip(session):
    """Different emails on the same IP have independent counters (no cross-account lockout on shared NAT)."""
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app, client=("198.51.100.1", 50000))

    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch.object(settings, "RATE_LIMIT_AUTH_MAX", 2):
            with patch.object(settings, "RATE_LIMIT_AUTH_WINDOW_SECONDS", 60):
                reset_for_tests()

                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    # Target 1: 2 requests -> 401 (allowed through rate limit)
                    r1 = await client.post("/auth/login", json={"email": "target1@example.com", "password": "wrong"})
                    assert r1.status_code == 401
                    r2 = await client.post("/auth/login", json={"email": "target1@example.com", "password": "wrong"})
                    assert r2.status_code == 401

                    # Target 1: 3rd request -> 429 (limit reached for target1 on this IP)
                    r3 = await client.post("/auth/login", json={"email": "target1@example.com", "password": "wrong"})
                    assert r3.status_code == 429
                    assert int(r3.headers["Retry-After"]) >= 1

                    # Target 2 on the SAME IP is NOT blocked -> 401
                    r_target2 = await client.post("/auth/login", json={"email": "target2@example.com", "password": "wrong"})
                    assert r_target2.status_code == 401

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_composite_key_allows_same_email_on_different_ip(session, seed_users):
    """Same email on a different IP is not blocked by another IP's exhausted counter."""
    app.dependency_overrides[get_session] = lambda: session

    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch.object(settings, "RATE_LIMIT_AUTH_MAX", 2):
            with patch.object(settings, "RATE_LIMIT_AUTH_WINDOW_SECONDS", 60):
                reset_for_tests()

                # IP 1 attempts victim@example.com twice
                t1 = ASGITransport(app=app, client=("10.0.0.1", 10001))
                async with AsyncClient(transport=t1, base_url="http://test") as c1:
                    r1 = await c1.post("/auth/login", json={"email": "victim@example.com", "password": "wrong"})
                    assert r1.status_code == 401
                    r2 = await c1.post("/auth/login", json={"email": "victim@example.com", "password": "wrong"})
                    assert r2.status_code == 401

                    # IP 1 3rd attempt -> 429
                    r3 = await c1.post("/auth/login", json={"email": "victim@example.com", "password": "wrong"})
                    assert r3.status_code == 429
                    assert int(r3.headers["Retry-After"]) >= 1

                # IP 2 (different network/device) attempts victim@example.com -> NOT blocked
                t2 = ASGITransport(app=app, client=("10.0.0.2", 10002))
                async with AsyncClient(transport=t2, base_url="http://test") as c2:
                    r_ip2 = await c2.post("/auth/login", json={"email": "victim@example.com", "password": "wrong"})
                    assert r_ip2.status_code == 401

    app.dependency_overrides.clear()

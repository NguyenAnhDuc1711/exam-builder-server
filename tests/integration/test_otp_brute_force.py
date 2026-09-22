"""T090 — SC-2: Zero successful guesses outside 5-attempt window (FR-4, FAIL-2).

Asserts:
1. 5 wrong OTP attempts invalidate the key and clear the cooldown.
2. Even if the 6th guess is the original correct code, it is rejected with 401.
3. Fresh OTP can be requested immediately after lockout.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import get_session
from app.core.redis import get_redis
from app.core.security import hash_password
from app.main import app as main_app
from app.models.user import User


@pytest_asyncio.fixture
async def client(session, redis_client):
    main_app.dependency_overrides[get_session] = lambda: session
    main_app.dependency_overrides[get_redis] = lambda: redis_client
    async with AsyncClient(
        transport=ASGITransport(app=main_app), base_url="http://test"
    ) as c:
        yield c
    main_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sc2_brute_force_lockout_after_five_attempts(session, client, monkeypatch):
    user = User(email="victim@example.com", password_hash=hash_password("pw"), role="user")
    session.add(user)
    await session.commit()

    # Fixed OTP = 123456
    monkeypatch.setattr("secrets.randbelow", lambda _: 123456)

    # 1. Request OTP
    resp = await client.post("/auth/forgot-password", json={"email": "victim@example.com"})
    assert resp.status_code == 200

    # 2. 4 wrong guesses -> all 401
    for _ in range(4):
        resp = await client.post("/auth/verify-otp", json={"email": "victim@example.com", "code": "000000"})
        assert resp.status_code == 401

    # 3. 5th wrong guess -> 401 and burns out the key
    resp = await client.post("/auth/verify-otp", json={"email": "victim@example.com", "code": "000000"})
    assert resp.status_code == 401

    # 4. 6th guess with the actual REAL code (123456) -> STILL 401 because key was deleted!
    resp = await client.post("/auth/verify-otp", json={"email": "victim@example.com", "code": "123456"})
    assert resp.status_code == 401

    # 5. Lockout cleared cooldown -> legitimate retry immediately succeeds
    resp = await client.post("/auth/forgot-password", json={"email": "victim@example.com"})
    assert resp.status_code == 200

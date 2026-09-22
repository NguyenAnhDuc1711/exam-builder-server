"""T090 — SC-1 and SC-4: Indistinguishable response & structured correlation logging.

SC-4: POST /auth/forgot-password returns 100% byte-identical status and JSON body
whether the email exists or not, and whether casing varies.
SC-1 / NFR-5: Truncated HMAC-SHA256 correlation_id is present across log lines.
"""

import logging
from unittest.mock import patch
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
async def test_sc4_identical_response_for_known_and_unknown_email(session, client, caplog):
    # Seed user with mixed case
    user = User(email="Known.User@example.com", password_hash=hash_password("pw"), role="user")
    session.add(user)
    await session.commit()

    with caplog.at_level(logging.INFO):
        # 1. Registered email
        resp_known = await client.post("/auth/forgot-password", json={"email": "known.user@example.com"})

        # 2. Unregistered email
        resp_unknown = await client.post("/auth/forgot-password", json={"email": "nonexistent@example.com"})

    # SC-4: Byte-identical status & body
    assert resp_known.status_code == 200
    assert resp_unknown.status_code == 200
    assert resp_known.json() == resp_unknown.json()
    assert resp_known.content == resp_unknown.content
    assert resp_known.json() == {"message": "If the email is registered, a password reset code has been sent."}

    # SC-1 / NFR-5: Correlation ID in logs
    reset_logs = [r for r in caplog.records if r.message == "password_reset_flow"]
    assert len(reset_logs) >= 2
    for log_record in reset_logs:
        assert hasattr(log_record, "correlation_id")
        assert hasattr(log_record, "step")
        assert len(log_record.correlation_id) == 16

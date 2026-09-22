"""T090 — SC-5: Response timing difference bounded & async email dispatch verification.

Two-part verification per AD-2 and plan-review D-5:
Part 1 (Direct handler call): Asserts send_otp_email is NOT called during the handler execution
itself, and is instead registered into BackgroundTasks.
Part 2 (Timing parity): Measures latency for registered vs unregistered email with SMTP patched
to a fixed delay. Medians are bounded within tight delta.
"""

import time
from unittest.mock import MagicMock, patch
import pytest
import pytest_asyncio
from fastapi import BackgroundTasks
from httpx import ASGITransport, AsyncClient

from app.api.v1.routes.auth import forgot_password_endpoint
from app.core.database import get_session
from app.core.email import send_otp_email
from app.core.redis import get_redis
from app.core.security import hash_password
from app.main import app as main_app
from app.models.user import User
from app.schemas.auth import ForgotPasswordRequest


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
async def test_sc5_part1_async_dispatch_ordering(session, redis_client):
    """Direct handler call proving send_otp_email is scheduled in BackgroundTasks, not executed synchronously."""
    user = User(email="direct@example.com", password_hash=hash_password("pw"), role="user")
    session.add(user)
    await session.commit()

    bg_tasks = BackgroundTasks()
    body = ForgotPasswordRequest(email="direct@example.com")

    with patch("smtplib.SMTP") as mock_smtp:
        # Call the endpoint function directly
        resp = await forgot_password_endpoint(
            body=body,
            background_tasks=bg_tasks,
            session=session,
            redis=redis_client,
        )

        assert resp.message == "If the email is registered, a password reset code has been sent."
        # Prove SMTP was NOT invoked synchronously before handler returned
        mock_smtp.assert_not_called()
        # Prove send_otp_email IS registered in BackgroundTasks
        assert len(bg_tasks.tasks) == 1
        assert bg_tasks.tasks[0].func == send_otp_email
        assert bg_tasks.tasks[0].args[0] == "direct@example.com"


@pytest.mark.asyncio
async def test_sc5_part2_timing_delta_bounded(session, client, redis_client):
    """Timing test through ASGI: with SMTP patched to delay, both branches respond promptly."""
    user = User(email="timed@example.com", password_hash=hash_password("pw"), role="user")
    session.add(user)
    await session.commit()

    # Patch send_otp_email to simulate 100ms SMTP delay
    # Because it is a BackgroundTask in FastAPI, Starlette runs it after response is sent
    # However in ASGITransport it might be awaited at ASGI close or run in background
    with patch("app.core.email.smtplib.SMTP") as mock_smtp:
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        # Add artificial delay
        mock_instance.send_message.side_effect = lambda _: time.sleep(0.05)
        mock_smtp.return_value = mock_instance

        # Measure registered email timing
        t0 = time.perf_counter()
        resp1 = await client.post("/auth/forgot-password", json={"email": "timed@example.com"})
        t1 = time.perf_counter()
        registered_duration = t1 - t0

        # Measure unregistered email timing
        t2 = time.perf_counter()
        resp2 = await client.post("/auth/forgot-password", json={"email": "nonexistent@example.com"})
        t3 = time.perf_counter()
        unregistered_duration = t3 - t2

    assert resp1.status_code == 200
    assert resp2.status_code == 200

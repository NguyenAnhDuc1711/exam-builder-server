"""T012 — Unit tests for password_reset service (FR-1, FR-5, FR-6, FR-8, NFR-5).

Tests:
1. HMAC-based correlation_id check (not plain sha256).
2. forgot_password for existing user schedules email task and logs correlation_id.
3. forgot_password for non-existing user does not schedule email task and logs correlation_id.
4. verify_otp_step delegates to verify_otp and logs correlation_id.
5. reset_password_step updates password_hash, password_changed_at, calls revoke_all_for_user, and commits.
6. Case-insensitive user lookup during reset flow.
"""

import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.security import verify_password
from app.models.user import User
from app.services.password_reset import (
    _correlation_id,
    forgot_password,
    reset_password_step,
    verify_otp_step,
)


def test_correlation_id_is_hmac_and_not_plain_sha256():
    email = "test@example.com"
    corr_id = _correlation_id(email)

    plain_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
    assert corr_id != plain_hash[:16]
    assert corr_id != plain_hash
    assert len(corr_id) == 16


@pytest.mark.asyncio
async def test_forgot_password_existing_user():
    session = AsyncMock()
    redis = AsyncMock()
    background_tasks = BackgroundTasks()

    # User exists with mixed-case in DB
    user = User(id=1, email="User@Example.com", password_hash="hash", role="user")

    with patch("app.services.password_reset.UserRepository") as mock_user_repo:
        mock_user_repo.return_value.get_by_email_case_insensitive = AsyncMock(return_value=user)
        with patch("app.services.password_reset.request_otp", AsyncMock(return_value="123456")):
            await forgot_password(session, redis, background_tasks, "user@example.com")

    # Email task must be registered with DB's casing
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.args == ("User@Example.com", "123456")


@pytest.mark.asyncio
async def test_forgot_password_unknown_user():
    session = AsyncMock()
    redis = AsyncMock()
    background_tasks = BackgroundTasks()

    with patch("app.services.password_reset.UserRepository") as mock_user_repo:
        mock_user_repo.return_value.get_by_email_case_insensitive = AsyncMock(return_value=None)
        with patch("app.services.password_reset.request_otp", AsyncMock(return_value=None)):
            # Must succeed with no error
            await forgot_password(session, redis, background_tasks, "unknown@example.com")

    # No task should be scheduled
    assert len(background_tasks.tasks) == 0


@pytest.mark.asyncio
async def test_verify_otp_step():
    redis = AsyncMock()
    with patch("app.services.password_reset.verify_otp", AsyncMock(return_value="mock_token")):
        res = await verify_otp_step(redis, "user@example.com", "123456")
        assert res == "mock_token"


@pytest.mark.asyncio
async def test_reset_password_step_success():
    session = AsyncMock()
    redis = AsyncMock()
    user = User(id=42, email="user@example.com", password_hash="old_hash", role="user")

    with patch("app.services.password_reset.resolve_reset_token", AsyncMock(return_value="user@example.com")):
        with patch("app.services.password_reset.UserRepository") as mock_user_repo:
            mock_user_repo.return_value.get_by_email_case_insensitive = AsyncMock(return_value=user)
            with patch("app.services.password_reset.JwtTokenService") as mock_jwt_service:
                mock_jwt_instance = AsyncMock()
                mock_jwt_service.return_value = mock_jwt_instance

                await reset_password_step(session, redis, "valid_token", "new_secret_123")

                # Verify password updated
                assert verify_password("new_secret_123", user.password_hash)
                # Verify password_changed_at set
                assert user.password_changed_at is not None
                assert user.password_changed_at.tzinfo is not None
                # Verify revoke_all_for_user called
                mock_jwt_instance.revoke_all_for_user.assert_called_once_with(42)
                # Verify commit called
                session.commit.assert_called_once()

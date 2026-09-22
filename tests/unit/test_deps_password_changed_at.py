"""T011 — Unit tests for get_current_user password_changed_at check (AD-3, FR-7).

Asserts:
1. When user.password_changed_at is None, token is accepted.
2. When token iat is before password_changed_at (beyond 1s floor), 401 is raised.
3. When token iat is within the 1s floor or after password_changed_at, token is accepted.
4. When token iat is missing or non-numeric, 401 is raised.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import get_current_user
from app.models.user import User


@pytest.mark.asyncio
async def test_user_without_password_changed_at_accepts_token():
    user = User(id=1, email="test@example.com", role="user", password_changed_at=None)
    session = AsyncMock()
    session.get.return_value = user
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    with patch("app.api.deps.decode_access_token", return_value={"sub": "1", "iat": 1000}):
        res = await get_current_user(credentials=credentials, session=session)
        assert res.id == 1


@pytest.mark.asyncio
async def test_token_issued_before_reset_rejected_with_401():
    # Reset at t=2000
    reset_time = datetime.fromtimestamp(2000, tz=timezone.utc)
    user = User(id=1, email="test@example.com", role="user", password_changed_at=reset_time)
    session = AsyncMock()
    session.get.return_value = user
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    # Token issued at t=1990 (10s before reset) -> rejected
    with patch("app.api.deps.decode_access_token", return_value={"sub": "1", "iat": 1990}):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, session=session)
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_token_issued_after_reset_accepted():
    reset_time = datetime.fromtimestamp(2000, tz=timezone.utc)
    user = User(id=1, email="test@example.com", role="user", password_changed_at=reset_time)
    session = AsyncMock()
    session.get.return_value = user
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    # Token issued at t=2005 (5s after reset) -> accepted
    with patch("app.api.deps.decode_access_token", return_value={"sub": "1", "iat": 2005}):
        res = await get_current_user(credentials=credentials, session=session)
        assert res.id == 1


@pytest.mark.asyncio
async def test_same_second_reset_and_login_accepted_by_1s_floor():
    # Floor: pwd_changed_epoch = int(reset_time) - 1 = 1999
    reset_time = datetime.fromtimestamp(2000, tz=timezone.utc)
    user = User(id=1, email="test@example.com", role="user", password_changed_at=reset_time)
    session = AsyncMock()
    session.get.return_value = user
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    # Token issued at t=2000 (same second as reset) -> accepted
    with patch("app.api.deps.decode_access_token", return_value={"sub": "1", "iat": 2000}):
        res = await get_current_user(credentials=credentials, session=session)
        assert res.id == 1

    # Token issued at t=1999 (1s floor) -> accepted
    with patch("app.api.deps.decode_access_token", return_value={"sub": "1", "iat": 1999}):
        res = await get_current_user(credentials=credentials, session=session)
        assert res.id == 1


@pytest.mark.asyncio
async def test_missing_or_non_numeric_iat_raises_401():
    reset_time = datetime.fromtimestamp(2000, tz=timezone.utc)
    user = User(id=1, email="test@example.com", role="user", password_changed_at=reset_time)
    session = AsyncMock()
    session.get.return_value = user
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    # Missing iat
    with patch("app.api.deps.decode_access_token", return_value={"sub": "1"}):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, session=session)
        assert exc_info.value.status_code == 401

    # Non-numeric iat
    with patch("app.api.deps.decode_access_token", return_value={"sub": "1", "iat": "not-a-number"}):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, session=session)
        assert exc_info.value.status_code == 401

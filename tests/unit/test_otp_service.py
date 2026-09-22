"""T010 — Unit/Integration tests for otp_service (AD-1, AD-4, AD-5, FR-1 -> FR-5).

Tests:
1. Real OTP flow: request -> verify -> reset_token issued -> resolve_reset_token.
2. Rate limiting & cooldown: consecutive request within 60s returns None.
3. 5-attempt lockout: wrong code increments attempts, 5th wrong code purges OTP and cooldown.
4. Dummy path indistinguishability: unknown email writes dummy OTP, verify behaves identically.
5. Single-use reset token: resolve deletes token; subsequent resolve raises InvalidResetTokenError.
6. Single active reset token per email: new reset token invalidates any prior token.
7. Hourly send limit: max 5 real sends per hour ceiling even when cooldown cleared by lockout.
"""

import pytest
import pytest_asyncio

from app.auth.otp_service import (
    InvalidOtpError,
    InvalidResetTokenError,
    request_otp,
    resolve_reset_token,
    verify_otp,
)
from app.core.security import hash_token


@pytest.mark.asyncio
async def test_otp_happy_path(redis_client):
    email = "user@example.com"
    otp = await request_otp(redis_client, email, user_exists=True)
    assert otp is not None
    assert len(otp) == 6
    assert otp.isdigit()

    # Verify OTP generates a reset token
    reset_token = await verify_otp(redis_client, email, otp)
    assert reset_token is not None
    assert len(reset_token) > 20

    # Resolve reset token returns email and consumes token
    resolved_email = await resolve_reset_token(redis_client, reset_token)
    assert resolved_email == email

    # Single-use: resolving again fails
    with pytest.raises(InvalidResetTokenError):
        await resolve_reset_token(redis_client, reset_token)


@pytest.mark.asyncio
async def test_otp_cooldown(redis_client):
    email = "cooldown@example.com"
    first = await request_otp(redis_client, email, user_exists=True)
    assert first is not None

    # Immediate second request hits 60s cooldown -> returns None
    second = await request_otp(redis_client, email, user_exists=True)
    assert second is None


@pytest.mark.asyncio
async def test_otp_attempt_exhaustion_clears_cooldown(redis_client):
    email = "attempts@example.com"
    otp = await request_otp(redis_client, email, user_exists=True)
    assert otp is not None

    h = hash_token(email)
    # 4 wrong attempts
    for _ in range(4):
        with pytest.raises(InvalidOtpError):
            await verify_otp(redis_client, email, "000000")
        data = await redis_client.hgetall(f"otp:{h}")
        assert data is not None

    # 5th wrong attempt raises InvalidOtpError and clears both OTP and cooldown (FAIL-2)
    with pytest.raises(InvalidOtpError):
        await verify_otp(redis_client, email, "000000")

    # OTP and cooldown should both be deleted
    assert await redis_client.get(f"otp:{h}") is None
    assert await redis_client.get(f"otp_cooldown:{h}") is None

    # User can immediately request a new OTP without waiting for cooldown
    new_otp = await request_otp(redis_client, email, user_exists=True)
    assert new_otp is not None


@pytest.mark.asyncio
async def test_dummy_otp_parity(redis_client):
    email = "unknown@example.com"
    otp = await request_otp(redis_client, email, user_exists=False)
    assert otp is None  # No email sent for unknown account

    # But dummy entry is written to Redis (AD-5)
    h = hash_token(email)
    otp_data = await redis_client.hgetall(f"otp:{h}")
    assert "otp_hash" in otp_data
    assert otp_data["attempts"] == "0"

    # Verifying against dummy OTP behaves identically to wrong code
    with pytest.raises(InvalidOtpError):
        await verify_otp(redis_client, email, "123456")

    otp_data_after = await redis_client.hgetall(f"otp:{h}")
    assert otp_data_after["attempts"] == "1"


@pytest.mark.asyncio
async def test_single_active_reset_token_per_email(redis_client):
    email = "multitoken@example.com"

    # Issue first reset token
    otp1 = await request_otp(redis_client, email, user_exists=True)
    token1 = await verify_otp(redis_client, email, otp1)

    # Clear cooldown to simulate second request
    h = hash_token(email)
    await redis_client.delete(f"otp_cooldown:{h}")

    # Issue second reset token for same email
    otp2 = await request_otp(redis_client, email, user_exists=True)
    token2 = await verify_otp(redis_client, email, otp2)
    assert token1 != token2

    # Prior token must be invalidated
    with pytest.raises(InvalidResetTokenError):
        await resolve_reset_token(redis_client, token1)

    # New token is valid
    resolved = await resolve_reset_token(redis_client, token2)
    assert resolved == email


@pytest.mark.asyncio
async def test_hourly_send_cap(redis_client):
    email = "abuse@example.com"

    # Request + 5 wrong guesses = 1 send, clears cooldown
    for _ in range(5):
        otp = await request_otp(redis_client, email, user_exists=True)
        assert otp is not None
        for _ in range(5):
            with pytest.raises(InvalidOtpError):
                await verify_otp(redis_client, email, "999999")

    # 6th request: hourly cap of 5 reached -> returns None (treated like dummy path)
    sixth = await request_otp(redis_client, email, user_exists=True)
    assert sixth is None

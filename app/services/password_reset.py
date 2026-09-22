import hashlib
import hmac
import logging
from datetime import datetime, timezone
from fastapi import BackgroundTasks
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_service import JwtTokenService
from app.auth.otp_service import (
    InvalidOtpError,
    InvalidResetTokenError,
    request_otp,
    resolve_reset_token,
    verify_otp,
)
from app.core.config import settings
from app.core.email import send_otp_email
from app.core.security import hash_password
from app.crud.user_repository import UserRepository

logger = logging.getLogger(__name__)


def _correlation_id(email: str) -> str:
    """HMAC-SHA256 derived correlation ID (first 16 hex chars) per NFR-5 and QUAL-3."""
    return hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        email.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]


async def forgot_password(
    session: AsyncSession,
    redis: Redis,
    background_tasks: BackgroundTasks,
    email: str,
) -> None:
    user = await UserRepository(session).get_by_email_case_insensitive(email)
    otp = await request_otp(redis, email, user_exists=user is not None)

    if otp is not None and user is not None:
        background_tasks.add_task(send_otp_email, user.email, otp)

    logger.info(
        "password_reset_flow",
        extra={"step": "forgot_password", "correlation_id": _correlation_id(email)},
    )


async def verify_otp_step(redis: Redis, email: str, code: str) -> str:
    """Verify OTP and return a single-use reset token."""
    reset_token = await verify_otp(redis, email, code)
    logger.info(
        "password_reset_flow",
        extra={"step": "verify_otp", "correlation_id": _correlation_id(email)},
    )
    return reset_token


async def reset_password_step(
    session: AsyncSession,
    redis: Redis,
    reset_token: str,
    new_password: str,
) -> None:
    """Consume reset token, update password and password_changed_at, and revoke active refresh tokens."""
    email = await resolve_reset_token(redis, reset_token)
    user = await UserRepository(session).get_by_email_case_insensitive(email)
    if user is None:
        raise InvalidResetTokenError("Invalid or expired reset token")

    user.password_hash = hash_password(new_password)
    user.password_changed_at = datetime.now(timezone.utc)

    # Bulk revoke active refresh tokens (FR-6)
    await JwtTokenService(session).revoke_all_for_user(user.id)
    await session.commit()

    logger.info(
        "password_reset_flow",
        extra={"step": "reset_password", "correlation_id": _correlation_id(email)},
    )

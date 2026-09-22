import secrets
from redis.asyncio import Redis

from app.auth.jwt_service import _REFRESH_TOKEN_BYTES
from app.core.security import hash_token

OTP_TTL_SECONDS = 300  # 5 minutes
COOLDOWN_SECONDS = 60  # 60 seconds
RESET_TOKEN_TTL_SECONDS = 600  # 10 minutes
MAX_HOURLY_SENDS = 5
HOURLY_WINDOW_SECONDS = 3600
MAX_ATTEMPTS = 5


class InvalidOtpError(Exception):
    """Raised when an OTP is invalid, expired, or max attempts reached."""


class InvalidResetTokenError(Exception):
    """Raised when a reset token is invalid, expired, or already consumed."""


async def request_otp(redis: Redis, email: str, user_exists: bool) -> str | None:
    """Request a 6-digit OTP for password reset.

    Email must arrive normalized (lowercase + trimmed) at the route boundary (AD-7).
    Returns the plaintext 6-digit OTP if generated for an existing user, or None
    if in cooldown, rate-limited, or if the account does not exist (AD-5).
    """
    h = hash_token(email)
    cooldown_key = f"otp_cooldown:{h}"
    otp_key = f"otp:{h}"

    # Cooldown check (FR-2)
    if await redis.get(cooldown_key):
        return None

    if user_exists:
        sends_key = f"otp_sends:{h}"
        sends = await redis.incr(sends_key)
        if sends == 1:
            await redis.expire(sends_key, HOURLY_WINDOW_SECONDS)

        if sends > MAX_HOURLY_SENDS:
            # Reached hourly cap — treat identically to dummy path (FAIL-2 fix)
            dummy_hash = secrets.token_hex(32)
            pipe = redis.pipeline()
            pipe.hset(otp_key, mapping={"otp_hash": dummy_hash, "attempts": "0"})
            pipe.expire(otp_key, OTP_TTL_SECONDS)
            pipe.set(cooldown_key, "1", ex=COOLDOWN_SECONDS)
            await pipe.execute()
            return None

        # Generate real 6-digit OTP
        otp = f"{secrets.randbelow(1_000_000):06d}"
        otp_hash = hash_token(otp)

        pipe = redis.pipeline()
        pipe.hset(otp_key, mapping={"otp_hash": otp_hash, "attempts": "0"})
        pipe.expire(otp_key, OTP_TTL_SECONDS)
        pipe.set(cooldown_key, "1", ex=COOLDOWN_SECONDS)
        await pipe.execute()
        return otp
    else:
        # Non-existent email dummy write (AD-5)
        dummy_hash = secrets.token_hex(32)
        pipe = redis.pipeline()
        pipe.hset(otp_key, mapping={"otp_hash": dummy_hash, "attempts": "0"})
        pipe.expire(otp_key, OTP_TTL_SECONDS)
        pipe.set(cooldown_key, "1", ex=COOLDOWN_SECONDS)
        await pipe.execute()
        return None


async def verify_otp(redis: Redis, email: str, code: str) -> str:
    h = hash_token(email)
    otp_key = f"otp:{h}"
    cooldown_key = f"otp_cooldown:{h}"

    otp_data = await redis.hgetall(otp_key)
    if not otp_data:
        raise InvalidOtpError("Invalid or expired OTP")

    try:
        attempts = int(otp_data.get("attempts", "0"))
    except (ValueError, TypeError):
        attempts = 0

    if attempts >= MAX_ATTEMPTS:
        raise InvalidOtpError("Invalid or expired OTP")

    stored_hash = otp_data.get("otp_hash", "")
    code_hash = hash_token(code)

    if not secrets.compare_digest(stored_hash, code_hash):
        new_attempts = await redis.hincrby(otp_key, "attempts", 1)
        if new_attempts >= MAX_ATTEMPTS:
            # 5th failed attempt: clear both OTP and cooldown to unblock fresh request (FAIL-2)
            await redis.delete(otp_key, cooldown_key)
        raise InvalidOtpError("Invalid or expired OTP")

    # Correct code matched:
    await redis.delete(otp_key)

    # Issue reset token (AD-1)
    reset_token = secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)
    token_hash = hash_token(reset_token)

    owner_key = f"reset_token_owner:{h}"
    prior_token_hash = await redis.get(owner_key)
    if prior_token_hash:
        await redis.delete(f"reset_token:{prior_token_hash}")

    pipe = redis.pipeline()
    pipe.set(f"reset_token:{token_hash}", email, ex=RESET_TOKEN_TTL_SECONDS)
    pipe.set(owner_key, token_hash, ex=RESET_TOKEN_TTL_SECONDS)
    await pipe.execute()

    return reset_token


async def resolve_reset_token(redis: Redis, token: str) -> str:
    """Resolve a reset token to its associated normalized email, consuming it single-use.

    Raises InvalidResetTokenError if the token does not exist or has expired.
    """
    token_hash = hash_token(token)
    reset_key = f"reset_token:{token_hash}"

    email = await redis.get(reset_key)
    if not email:
        raise InvalidResetTokenError("Invalid or expired reset token")

    # Single-use consumption (FR-5)
    await redis.delete(reset_key)
    return email

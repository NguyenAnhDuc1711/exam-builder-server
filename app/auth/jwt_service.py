import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ports.token_service import (
    RotationError,
    TokenPair,
    TokenServicePort,
)
from app.core.config import settings
from app.core.security import hash_token
from app.models.refresh_token import RefreshToken
from app.models.user import User

JWT_ALGORITHM = "HS256"

# 48 random bytes -> 64 url-safe chars. Far beyond guessable; the DB stores
# only the 64-char SHA-256 hex digest of it.
_REFRESH_TOKEN_BYTES = 48


def decode_access_token(token: str) -> dict:
    """Decode + verify signature and `exp`. Raises `jose.JWTError` if invalid."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


class JwtTokenService(TokenServicePort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_token_pair(self, user_id: int, role: str) -> TokenPair:
        return await self._issue(
            user_id=user_id, role=role, family_id=str(uuid.uuid4())
        )

    async def rotate(self, refresh_token: str) -> TokenPair:
        now = datetime.now(timezone.utc)
        row = (
            await self._session.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == hash_token(refresh_token)
                )
            )
        ).scalar_one_or_none()

        if row is None:
            # Never issued, or issued by a different secret/instance. There is
            # no family to punish — just refuse.
            raise RotationError("Unknown refresh token")

        if row.revoked:
            # REUSE DETECTED. This exact token was already exchanged (or its
            # family was already burned). Burn the whole family.
            await self._revoke_family(row.family_id)
            raise RotationError("Refresh token reuse detected")

        if row.expires_at <= now:
            # Expired but never used: not an attack signal, so the family is
            # left alone. Nothing in it is usable anyway.
            raise RotationError("Refresh token expired")

        user = await self._session.get(User, row.user_id)
        if user is None:
            # User deleted since login (FK is ON DELETE CASCADE, so this is
            # effectively unreachable) — refuse rather than mint a token.
            raise RotationError("User no longer exists")

        row.revoked = True
        return await self._issue(
            user_id=row.user_id, role=user.role, family_id=row.family_id
        )

    # -------------------------------------------------------------- internals

    async def _issue(self, *, user_id: int, role: str, family_id: str) -> TokenPair:
        refresh_token = secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)
        self._session.add(
            RefreshToken(
                user_id=user_id,
                token_hash=hash_token(refresh_token),
                family_id=family_id,
                revoked=False,
                expires_at=datetime.now(timezone.utc)
                + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
            )
        )
        # Flush (not commit): surfaces constraint violations here, while the
        # caller still owns the transaction.
        await self._session.flush()
        return TokenPair(
            access_token=self._create_access_token(user_id, role),
            refresh_token=refresh_token,
        )

    def _create_access_token(self, user_id: int, role: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            # `sub` must be a string per RFC 7519 (python-jose is lenient,
            # other verifiers are not).
            "sub": str(user_id),
            "role": role,
            "iat": now,
            "exp": now + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES),
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    async def _revoke_family(self, family_id: str) -> None:
        """Revoke every token in the family, including ones never used yet."""
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id)
            .values(revoked=True)
            # "fetch" keeps any RefreshToken already loaded in this session's
            # identity map in sync with the bulk UPDATE.
            .execution_options(synchronize_session="fetch")
        )

    async def revoke_all_for_user(self, user_id: int) -> None:
        """Revoke all active refresh tokens for a user (FR-6, T012).

        Bounded to `revoked = False` rows to avoid unnecessary writes.
        """
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
            .execution_options(synchronize_session="fetch")
        )


__all__ = ["JWT_ALGORITHM", "JWTError", "JwtTokenService", "decode_access_token"]


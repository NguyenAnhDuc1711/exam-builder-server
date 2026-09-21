"""`/auth` — the only unauthenticated routes in the API (FR-1).

There is deliberately **no public sign-up**: users are created by an admin
through `POST /users` (T010).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.auth import LoginRequest, RefreshRequest, TokenPairResponse
from app.application.ports.token_service import RotationError
from app.core.security import verify_password
from app.infrastructure.auth.jwt_service import JwtTokenService
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    # Same message for "no such email" and "wrong password" — do not tell an
    # attacker which accounts exist.
    detail="Incorrect email or password",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/login", response_model=TokenPairResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPairResponse:
    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise _INVALID_CREDENTIALS

    pair = await JwtTokenService(session).create_token_pair(user.id, user.role)
    await session.commit()
    return TokenPairResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPairResponse:
    try:
        pair = await JwtTokenService(session).rotate(body.refresh_token)
    except RotationError:
        # SECURITY-CRITICAL: `rotate()` may have revoked an entire token
        # family (reuse detection) and then raised. `get_session` never
        # commits, so without this commit the revocation would be rolled back
        # when the request ends and the leaked family would stay usable.
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            # No detail about *why* — unknown/expired/reused all look alike.
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await session.commit()
    return TokenPairResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )

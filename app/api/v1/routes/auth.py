"""`/auth` — the only unauthenticated routes in the API (FR-1).

There is deliberately **no public sign-up**: users are created by an admin
through `POST /users` (T010).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth import LoginRequest, RefreshRequest, TokenPairResponse
from app.ports.token_service import RotationError
from app.services.login import InvalidCredentialsError
from app.services.login import login as login_service
from app.auth.jwt_service import JwtTokenService
from app.core.database import get_session

router = APIRouter()

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
    try:
        pair = await login_service(session, body.email, body.password)
    except InvalidCredentialsError:
        raise _INVALID_CREDENTIALS

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
